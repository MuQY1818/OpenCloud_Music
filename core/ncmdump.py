import os
import json
import base64
import struct
import logging
import binascii
from glob import glob
from tqdm.auto import tqdm
from textwrap import dedent
from Crypto.Cipher import AES
from multiprocessing import Pool


class TqdmLoggingHandler(logging.StreamHandler):
    """Avoid tqdm progress bar interruption by logger's output to console"""
    # see logging.StreamHandler.eval method:
    # https://github.com/python/cpython/blob/d2e2534751fd675c4d5d3adc208bf4fc984da7bf/Lib/logging/__init__.py#L1082-L1091
    # and tqdm.write method:
    # https://github.com/tqdm/tqdm/blob/f86104a1f30c38e6f80bfd8fb16d5fcde1e7749f/tqdm/std.py#L614-L620

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, end=self.terminator)
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)
handler = TqdmLoggingHandler()
fmt = '%(levelname)7s [%(asctime)s] %(message)s'
datefmt = '%Y-%m-%d %H:%M:%S'
handler.setFormatter(logging.Formatter(fmt, datefmt))
log.addHandler(handler)


def audio_format_of(header):
    """Return a file extension for a decrypted audio header, or None."""
    if not header:
        return None
    if header[:4] == b'fLaC':
        return 'flac'
    if header[:3] == b'ID3':
        return 'mp3'
    if len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
        return 'mp3'
    if len(header) >= 12 and header[4:8] == b'ftyp':
        return 'm4a'
    if header[:4] == b'OggS':
        return 'ogg'
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WAVE':
        return 'wav'
    return None


def _read_exact(fileobj, size):
    data = fileobj.read(size)
    if len(data) != size:
        raise ValueError(f'truncated NCM file, expected {size} bytes')
    return data


def _read_u32(fileobj):
    return struct.unpack('<I', _read_exact(fileobj, 4))[0]


def _safe_audio_format(fmt):
    fmt = str(fmt or 'mp3').lower().strip().lstrip('.')
    if 2 <= len(fmt) <= 4 and fmt.isalnum():
        return fmt
    return 'mp3'


def _file_has_audio_header(path):
    try:
        with open(path, 'rb') as existing:
            return audio_format_of(existing.read(16)) is not None
    except OSError:
        return False


def _read_cover_frame(fileobj):
    """Consume the cover frame and return the embedded image bytes.

    Bytes after the metadata block:

        crc32            u32
        version          u8
        cover_frame_len  u32
        image_len        u32
        image            image_len bytes
        unused           (cover_frame_len - image_len) bytes

    Older dumps skipped five bytes after the CRC and treated the rest as
    audio. That matches files whose cover frame is only the image. macOS
    client 3.x still writes a cover frame when the image length is 0, and
    decrypting those extra bytes makes the MP3 or FLAC unplayable.
    """
    _read_exact(fileobj, 4)
    _read_exact(fileobj, 1)
    cover_frame_len = _read_u32(fileobj)
    image_len = _read_u32(fileobj)
    if image_len > cover_frame_len:
        raise ValueError(
            f'invalid NCM cover frame: image length {image_len} exceeds frame {cover_frame_len}'
        )
    position = fileobj.tell()
    remaining = fileobj.seek(0, os.SEEK_END) - position
    fileobj.seek(position)
    if cover_frame_len > remaining:
        raise ValueError('invalid NCM cover frame: length exceeds remaining file')
    image_data = _read_exact(fileobj, image_len) if image_len else b''
    extra = cover_frame_len - image_len
    if extra:
        _read_exact(fileobj, extra)
        log.info(f'Skipped {extra} unused cover-frame bytes')
    return image_data


def dump_single_file(filepath):
    try:
        if os.path.splitext(filepath)[1].lower() != '.ncm':
            return None
        stem = os.path.splitext(os.path.basename(filepath))[0]
        directory = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()
        log.info(f'Converting "{filepath}"')

        # hex to str
        core_key = binascii.a2b_hex('687A4852416D736F356B496E62617857')
        meta_key = binascii.a2b_hex('2331346C6A6B5F215C5D2630553C2728')
        unpad = lambda s: s[0:-(s[-1] if isinstance(s[-1], int) else ord(s[-1]))]
        with open(filepath, 'rb') as f:
            header = f.read(8)
            if header != b'CTENFDAM':
                raise ValueError(f'not an ncm file: {filepath}')
            f.seek(2, os.SEEK_CUR)
            key_length = f.read(4)
            key_length = struct.unpack('<I', bytes(key_length))[0]
            key_data = f.read(key_length)
            key_data_array = bytearray(key_data)
            for i in range(0, len(key_data_array)):
                key_data_array[i] ^= 0x64
            key_data = bytes(key_data_array)
            cryptor = AES.new(core_key, AES.MODE_ECB)
            key_data = unpad(cryptor.decrypt(key_data))[17:]
            key_length = len(key_data)
            key_data = bytearray(key_data)
            key_box = bytearray(range(256))

            c = 0
            last_byte = 0
            key_offset = 0
            for i in range(256):
                swap = key_box[i]
                c = (swap + last_byte + key_data[key_offset]) & 0xff
                key_offset += 1
                if key_offset >= key_length:
                    key_offset = 0
                key_box[i] = key_box[c]
                key_box[c] = swap
                last_byte = c

            meta_length = f.read(4)
            meta_length = struct.unpack('<I', bytes(meta_length))[0]
            meta_data = f.read(meta_length)
            meta_data_array = bytearray(meta_data)
            for i in range(0, len(meta_data_array)):
                meta_data_array[i] ^= 0x63
            meta_data = bytes(meta_data_array)
            meta_data = base64.b64decode(meta_data[22:])
            cryptor = AES.new(meta_key, AES.MODE_ECB)
            meta_data = unpad(cryptor.decrypt(meta_data)).decode('utf-8')[6:]
            meta_data = json.loads(meta_data)

            _read_cover_frame(f)
            audio_format = _safe_audio_format(meta_data.get('format'))
            target_filename = os.path.join(directory, f'{stem}.{audio_format}')
            if os.path.isfile(target_filename) and _file_has_audio_header(target_filename):
                log.warning(f'Skipping "{filepath}" due to existing file "{target_filename}"')
                return os.path.abspath(target_filename)

            detected_format = None
            first_chunk = True
            with open(target_filename, 'wb') as m:
                while True:
                    chunk = bytearray(f.read(0x8000))
                    chunk_length = len(chunk)
                    if not chunk:
                        break
                    for i in range(1, chunk_length + 1):
                        j = i & 0xff
                        chunk[i - 1] ^= key_box[(key_box[j] + key_box[(key_box[j] + j) & 0xff]) & 0xff]
                    if first_chunk:
                        detected_format = audio_format_of(chunk)
                        first_chunk = False
                    m.write(chunk)

        if detected_format and detected_format != audio_format:
            renamed = os.path.join(directory, f'{stem}.{detected_format}')
            os.replace(target_filename, renamed)
            target_filename = renamed
        target_filename = os.path.abspath(target_filename)
        log.info(f'Converted file saved at "{target_filename}"')
        return target_filename

    except KeyboardInterrupt:
        log.warning('Aborted')
        quit()


def list_filepaths(path):
    if os.path.isfile(path):
        return [path]
    elif os.path.isdir(path):
        return [fp for p in glob(f'{path}/*') for fp in list_filepaths(p)]
    else:
        raise ValueError(f'path not recognized: {path}')


def dump(*paths, output_dir=None, n_workers=None):
    if n_workers is None:
        n_workers = 1
    header = dedent(r'''
                   _  _  ___ __  __ ___  _   _ __  __ ___
         _ __ _  _| \| |/ __|  \/  |   \| | | |  \/  | _ \
        | '_ \ || | .` | (__| |\/| | |) | |_| | |\/| |  _/
        | .__/\_, |_|\_|\___|_|  |_|___/ \___/|_|  |_|_|  
        |_|   |__/                                        
                            pyNCMDUMP                     
            https://github.com/allenfrostline/pyNCMDUMP  
    ''')
    for line in header.split('\n'):
        log.info(line)

    all_filepaths = [fp for p in paths for fp in list_filepaths(p)]
    if n_workers > 1:
        log.info(f'Running pyNCMDUMP with up to {n_workers} parallel workers')
        with Pool(processes=n_workers) as p:
            converted = list(p.map(dump_single_file, all_filepaths))
    else:
        log.info('Running pyNCMDUMP on single-worker mode')
        converted = []
        for fp in tqdm(all_filepaths, leave=False):
            converted.append(dump_single_file(fp))
    log.info('All finished')
    return [path for path in converted if path]


if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser(description='pyNCMDUMP command-line interface')
    parser.add_argument(
        'paths',
        metavar='paths',
        type=str,
        nargs='+',
        help='one or more paths to source files'
    )
    parser.add_argument(
        '-w', '--workers',
        metavar='',
        type=int,
        help=f'parallel convertion when set to more than 1 workers (default: 1)',
        default=1
    )
    args = parser.parse_args()
    dump(*args.paths, n_workers=args.workers)