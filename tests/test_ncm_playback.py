import base64
import json
import os
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest import mock

import requests

from Crypto.Cipher import AES

from core import ncmdump
from core.metadata import (
    _choose_song,
    convert_ncm_to_mp3,
    embed_tags,
    get_cover_data_from_tags,
    get_song_metadata,
    has_audio_header,
    update_and_embed_metadata,
)

CORE_KEY = bytes.fromhex('687A4852416D736F356B496E62617857')
META_KEY = bytes.fromhex('2331346C6A6B5F215C5D2630553C2728')
META_PREFIX = b"163 key(Don't modify):"
RC4_KEY = b'secret-key'


def _pkcs7(data):
    pad = 16 - (len(data) % 16)
    return data + bytes([pad]) * pad


def _build_key_box(key):
    key_box = bytearray(range(256))
    last_byte = 0
    key_offset = 0
    for i in range(256):
        swap = key_box[i]
        last_byte = (swap + last_byte + key[key_offset]) & 0xff
        key_offset += 1
        if key_offset >= len(key):
            key_offset = 0
        key_box[i] = key_box[last_byte]
        key_box[last_byte] = swap
    return key_box


def _xor_audio(data, key_box):
    output = bytearray()
    for offset in range(0, len(data), 0x8000):
        chunk = bytearray(data[offset:offset + 0x8000])
        for i in range(1, len(chunk) + 1):
            j = i & 0xff
            chunk[i - 1] ^= key_box[(key_box[j] + key_box[(key_box[j] + j) & 0xff]) & 0xff]
        output.extend(chunk)
    return bytes(output)


def _encrypt_key(rc4_key):
    plain = _pkcs7(b'neteasecloudmusic' + rc4_key)
    encrypted = AES.new(CORE_KEY, AES.MODE_ECB).encrypt(plain)
    return bytes(byte ^ 0x64 for byte in encrypted)


def _encrypt_meta(fmt):
    payload = b'music:' + json.dumps({'format': fmt, 'musicName': 'Tone'}).encode()
    encrypted = AES.new(META_KEY, AES.MODE_ECB).encrypt(_pkcs7(payload))
    wrapped = META_PREFIX + base64.b64encode(encrypted)
    return bytes(byte ^ 0x63 for byte in wrapped)


def build_ncm(path, audio, fmt, image=b'', extra=b'', rc4_key=RC4_KEY):
    """Write an NCM container.

    extra is the unused tail of the cover frame. macOS client 3.x leaves
    this non-empty even when the embedded image is missing.
    """
    assert len(META_PREFIX) == 22
    key_blob = _encrypt_key(rc4_key)
    meta_blob = _encrypt_meta(fmt)
    cover_frame_len = len(image) + len(extra)
    parts = [
        b'CTENFDAM',
        b'\x00\x00',
        struct.pack('<I', len(key_blob)),
        key_blob,
        struct.pack('<I', len(meta_blob)),
        meta_blob,
        struct.pack('<I', 0),
        b'\x01',
        struct.pack('<I', cover_frame_len),
        struct.pack('<I', len(image)),
        image,
        extra,
        _xor_audio(audio, _build_key_box(rc4_key)),
    ]
    with open(path, 'wb') as ncm_file:
        ncm_file.write(b''.join(parts))


def legacy_decrypt(path, rc4_key=RC4_KEY):
    """Old parser: skip five bytes after the CRC and ignore cover_frame_len."""
    key_box = _build_key_box(rc4_key)
    with open(path, 'rb') as ncm_file:
        if ncm_file.read(8) != b'CTENFDAM':
            raise AssertionError('bad test fixture')
        ncm_file.seek(2, os.SEEK_CUR)
        key_length = struct.unpack('<I', ncm_file.read(4))[0]
        ncm_file.seek(key_length, os.SEEK_CUR)
        meta_length = struct.unpack('<I', ncm_file.read(4))[0]
        ncm_file.seek(meta_length, os.SEEK_CUR)
        ncm_file.read(4)
        ncm_file.seek(5, os.SEEK_CUR)
        image_size = struct.unpack('<I', ncm_file.read(4))[0]
        ncm_file.read(image_size)
        return _xor_audio(ncm_file.read(), key_box)


def _ffmpeg_audio(path, codec):
    subprocess.run(
        [
            'ffmpeg', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.4',
            path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    with open(path, 'rb') as audio_file:
        return audio_file.read()


def _ffprobe(path):
    return subprocess.run(
        [
            'ffprobe', '-v', 'error',
            '-show_entries', 'format=format_name',
            '-of', 'default=nw=1:nk=1',
            path,
        ],
        capture_output=True,
        text=True,
    )


def _ffmpeg_decode(path):
    """Return a completed decode. Extension sniffing is not enough: a shifted
    NCM dump can still be labeled FLAC while producing zero audio packets.
    """
    return subprocess.run(
        ['ffmpeg', '-v', 'error', '-i', path, '-f', 'null', '-'],
        capture_output=True,
        text=True,
    )


class NcmDecryptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.mp3 = _ffmpeg_audio(os.path.join(cls._temp.name, 'tone.mp3'), 'mp3')
        cls.flac = _ffmpeg_audio(os.path.join(cls._temp.name, 'tone.flac'), 'flac')

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def test_classic_file_still_decrypts(self):
        ncm_path = os.path.join(self._temp.name, 'classic.ncm')
        build_ncm(ncm_path, self.mp3, 'mp3', image=b'\xff\xd8' + b'\x11' * 40)
        output = ncmdump.dump_single_file(ncm_path)
        with open(output, 'rb') as audio_file:
            self.assertEqual(audio_file.read(), self.mp3)
        self.assertEqual(legacy_decrypt(ncm_path), self.mp3)
        probed = _ffprobe(output)
        self.assertEqual(probed.returncode, 0, probed.stderr)
        self.assertIn('mp3', probed.stdout)
        decoded = _ffmpeg_decode(output)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)

    def test_macos_client_3_cover_frame_decrypts_to_playable_audio(self):
        ncm_path = os.path.join(self._temp.name, 'mac3.ncm')
        extra = b'\x5a' * 64
        build_ncm(ncm_path, self.flac, 'flac', image=b'', extra=extra)
        output = ncmdump.dump_single_file(ncm_path)
        self.assertTrue(output.endswith('.flac'))
        with open(output, 'rb') as audio_file:
            self.assertEqual(audio_file.read(), self.flac)
        probed = _ffprobe(output)
        self.assertEqual(probed.returncode, 0, probed.stderr)
        self.assertIn('flac', probed.stdout)
        decoded = _ffmpeg_decode(output)
        self.assertEqual(decoded.returncode, 0, decoded.stderr)

        legacy = legacy_decrypt(ncm_path)
        self.assertNotEqual(legacy, self.flac)
        self.assertNotEqual(legacy[:4], b'fLaC')
        legacy_path = os.path.join(self._temp.name, 'mac3-legacy.flac')
        with open(legacy_path, 'wb') as legacy_file:
            legacy_file.write(legacy)
        legacy_decoded = _ffmpeg_decode(legacy_path)
        self.assertNotEqual(legacy_decoded.returncode, 0, legacy_decoded.stderr)
        self.assertFalse(has_audio_header(legacy_path))

    def test_cover_image_plus_extra_padding_roundtrip(self):
        ncm_path = os.path.join(self._temp.name, 'both.ncm')
        build_ncm(
            ncm_path,
            self.mp3,
            'mp3',
            image=b'\xff\xd8\xff' + b'\x22' * 20,
            extra=b'\x33' * 17,
        )
        output = ncmdump.dump_single_file(ncm_path)
        with open(output, 'rb') as audio_file:
            self.assertEqual(audio_file.read(), self.mp3)
        self.assertNotEqual(legacy_decrypt(ncm_path), self.mp3)

    def test_sniff_renames_when_metadata_format_is_wrong(self):
        ncm_path = os.path.join(self._temp.name, 'mislabeled.ncm')
        build_ncm(ncm_path, self.flac, 'mp3', extra=b'\x44' * 8)
        output = ncmdump.dump_single_file(ncm_path)
        self.assertTrue(output.endswith('.flac'))
        with open(output, 'rb') as audio_file:
            self.assertEqual(audio_file.read(), self.flac)

    def test_convert_keeps_flac_and_replaces_unplayable_output(self):
        work = tempfile.mkdtemp(dir=self._temp.name)
        previous = os.getcwd()
        try:
            os.chdir(work)
            source_dir = os.path.join(work, 'src')
            os.makedirs(source_dir)
            ncm_path = os.path.join(source_dir, 'song.ncm')
            build_ncm(ncm_path, self.flac, 'flac', extra=b'\x66' * 32)
            os.makedirs('output')
            with open(os.path.join('output', 'song.mp3'), 'wb') as stale:
                stale.write(b'not an mp3')
            converted = convert_ncm_to_mp3(ncm_path)
            self.assertTrue(converted.endswith(os.path.join('output', 'song.flac')))
            self.assertTrue(os.path.isabs(converted))
            with open(converted, 'rb') as audio_file:
                self.assertEqual(audio_file.read(), self.flac)
            self.assertFalse(os.path.exists(os.path.join('output', 'song.mp3')))
            self.assertEqual(_ffprobe(converted).returncode, 0)
        finally:
            os.chdir(previous)
            shutil.rmtree(work)


class MetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp = tempfile.TemporaryDirectory()
        cls.mp3 = os.path.join(cls._temp.name, 'song.mp3')
        cls.flac = os.path.join(cls._temp.name, 'song.flac')
        _ffmpeg_audio(cls.mp3, 'mp3')
        _ffmpeg_audio(cls.flac, 'flac')

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def test_choose_song_prefers_exact_title_over_covers(self):
        songs = [
            {'id': 1, 'name': '晴天 (原唱 周杰伦)', 'artists': [{'name': 'RyaVocal'}]},
            {'id': 2, 'name': '晴天', 'artists': [{'name': 'Jay'}]},
            {'id': 3, 'name': '晴天(深情版)', 'artists': [{'name': 'Lucky小爱'}]},
        ]
        self.assertEqual(_choose_song(songs, '晴天', '周杰伦')['id'], 2)
        self.assertEqual(_choose_song(songs, '晴天(深情版)', 'Lucky小爱')['id'], 3)

    def test_embed_and_read_mp3_and_flac(self):
        cover = b'\xff\xd8\xff\xd9'
        lyrics = '[00:01.00]hello'
        for path in (self.mp3, self.flac):
            embed_tags(path, '晴天', '周杰伦', album='叶惠美', lyrics=lyrics, cover_data=cover)
            metadata = get_song_metadata(path)
            self.assertEqual(metadata['title'], '晴天')
            self.assertEqual(metadata['artist'], '周杰伦')
            self.assertIn('hello', metadata['lyrics'])
            self.assertGreater(metadata['duration'], 0)
            self.assertEqual(get_cover_data_from_tags(path), cover)
            self.assertTrue(os.path.isabs(metadata['path']))

    def test_online_metadata_failure_does_not_change_audio(self):
        with open(self.mp3, 'rb') as audio_file:
            before = audio_file.read()
        with mock.patch(
            'core.metadata.requests.get',
            side_effect=requests.ConnectionError('offline'),
        ):
            update_and_embed_metadata(self.mp3, '晴天', '周杰伦')
        with open(self.mp3, 'rb') as audio_file:
            self.assertEqual(audio_file.read(), before)

    def test_online_metadata_embeds_without_touching_audio_bytes_prefix(self):
        def fake_get(url, params=None, headers=None, timeout=None):
            response = mock.Mock()
            response.content = b'\xff\xd8\xff\xd9'
            response.raise_for_status.return_value = None
            if url.endswith('/api/search/get'):
                response.json.return_value = {
                    'code': 200,
                    'result': {'songs': [{
                        'id': 42,
                        'name': '晴天',
                        'artists': [{'name': '周杰伦'}],
                        'album': {'name': '叶惠美'},
                    }]},
                }
            elif url.endswith('/api/song/lyric'):
                response.json.return_value = {'lrc': {'lyric': '[00:01.00]故事'}}
            elif url.endswith('/api/song/detail/'):
                response.json.return_value = {'songs': [{
                    'name': '晴天',
                    'artists': [{'name': '周杰伦'}],
                    'album': {'name': '叶惠美', 'picUrl': 'https://example.test/cover.jpg'},
                }]}
            elif url == 'https://example.test/cover.jpg':
                pass
            else:
                raise AssertionError(url)
            return response

        with mock.patch('core.metadata.requests.get', side_effect=fake_get):
            update_and_embed_metadata(self.mp3, '', '')
        metadata = get_song_metadata(self.mp3)
        self.assertEqual(metadata['title'], '晴天')
        self.assertEqual(metadata['artist'], '周杰伦')
        self.assertIn('故事', metadata['lyrics'])
        self.assertEqual(get_cover_data_from_tags(self.mp3), b'\xff\xd8\xff\xd9')
        self.assertEqual(_ffprobe(self.mp3).returncode, 0)


if __name__ == '__main__':
    unittest.main()
