import os
import shutil
import traceback

import requests
from mutagen.flac import FLAC, Picture
from mutagen.id3 import APIC, ID3, TALB, TIT2, TPE1, USLT
from mutagen.mp3 import MP3

from core import ncmdump

# Playback does not depend on this. pyncm was removed from PyPI in May 2026;
# the same title, lyric, and cover fields are still available from the public
# NetEase endpoints below. A failure here leaves the decrypted audio untouched.
_API = 'https://music.163.com'
_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://music.163.com/',
}
PLAYABLE_EXTENSIONS = {'.mp3', '.flac', '.m4a', '.ogg', '.wav'}


def has_audio_header(song_path):
    try:
        with open(song_path, 'rb') as audio_file:
            return ncmdump.audio_format_of(audio_file.read(16)) is not None
    except OSError:
        return False


def _fallback_metadata(song_path):
    return {
        'path': os.path.abspath(song_path),
        'title': os.path.splitext(os.path.basename(song_path))[0],
        'artist': '未知艺术家',
        'duration': 0,
        'lyrics': None,
        'cover_pixmap': None,
    }


def _text(value, default):
    if value is None:
        return default
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        value = value[0]
    text = str(value).strip()
    return text or default


def get_song_metadata(song_path):
    song_path = os.path.abspath(song_path)
    if not os.path.isfile(song_path):
        return None
    try:
        ext = os.path.splitext(song_path)[1].lower()
        if ext == '.flac':
            return _metadata_from_flac(song_path)
        if ext == '.mp3':
            return _metadata_from_mp3(song_path)
        return _fallback_metadata(song_path)
    except Exception:
        traceback.print_exc()
        return _fallback_metadata(song_path)


def _frame_text(frame, default):
    if frame is None:
        return default
    if hasattr(frame, 'text'):
        return _text(frame.text, default)
    return _text(frame, default)


def _metadata_from_mp3(song_path):
    audio = MP3(song_path, ID3=ID3)
    tag = audio.tags
    lyrics = None
    if tag is not None:
        for key in tag.keys():
            if key.startswith('USLT'):
                lyrics = _text(tag[key].text, None)
                break
    metadata = _fallback_metadata(song_path)
    metadata.update({
        'title': _frame_text(None if tag is None else tag.get('TIT2'), metadata['title']),
        'artist': _frame_text(None if tag is None else tag.get('TPE1'), metadata['artist']),
        'duration': getattr(audio.info, 'length', 0) or 0,
        'lyrics': lyrics,
    })
    return metadata


def _metadata_from_flac(song_path):
    audio = FLAC(song_path)
    lyrics = None
    for key in ('lyrics', 'unsyncedlyrics'):
        if audio.get(key):
            lyrics = _text(audio.get(key), None)
            break
    metadata = _fallback_metadata(song_path)
    metadata.update({
        'title': _text(audio.get('title'), metadata['title']),
        'artist': _text(audio.get('artist'), metadata['artist']),
        'duration': getattr(audio.info, 'length', 0) or 0,
        'lyrics': lyrics,
    })
    return metadata


def get_cover_data_from_tags(song_path):
    try:
        ext = os.path.splitext(song_path)[1].lower()
        if ext == '.flac':
            audio = FLAC(song_path)
            if audio.pictures:
                return audio.pictures[0].data
            return None
        audio = MP3(song_path, ID3=ID3)
        tag = audio.tags
        if tag is None:
            return None
        for key in tag.keys():
            if key.startswith('APIC'):
                return tag[key].data
    except Exception:
        return None
    return None


def _remove_stale_output(output_dir, destination_path):
    stem = os.path.splitext(os.path.basename(destination_path))[0]
    for name in os.listdir(output_dir):
        candidate = os.path.join(output_dir, name)
        if candidate == destination_path:
            continue
        if os.path.splitext(name)[0] != stem:
            continue
        if os.path.splitext(name)[1].lower() not in PLAYABLE_EXTENSIONS:
            continue
        if not has_audio_header(candidate):
            os.remove(candidate)


def convert_ncm_to_mp3(ncm_path):
    """Decrypt one .ncm file into ./output and return the audio path.

    The name is kept for existing callers. The result is .mp3 or .flac,
    whichever format is inside the container.
    """
    output_dir = os.path.abspath('output')
    os.makedirs(output_dir, exist_ok=True)
    try:
        produced = ncmdump.dump(os.path.abspath(ncm_path))
    except Exception:
        traceback.print_exc()
        return None
    if not produced:
        return None

    source_path = produced[0]
    if not source_path or not os.path.isfile(source_path):
        return None
    destination_path = os.path.join(output_dir, os.path.basename(source_path))
    if os.path.abspath(source_path) != os.path.abspath(destination_path):
        if os.path.exists(destination_path):
            os.remove(destination_path)
        shutil.move(source_path, destination_path)
    _remove_stale_output(output_dir, destination_path)
    return os.path.abspath(destination_path)


def _image_mime(cover_data):
    if cover_data.startswith(b'\x89PNG'):
        return 'image/png'
    return 'image/jpeg'


def embed_tags(audio_path, title, artist, album='', lyrics=None, cover_data=None):
    ext = os.path.splitext(audio_path)[1].lower()
    if ext == '.flac':
        _embed_flac_tags(audio_path, title, artist, album, lyrics, cover_data)
    elif ext == '.mp3':
        _embed_mp3_tags(audio_path, title, artist, album, lyrics, cover_data)


def _embed_mp3_tags(audio_path, title, artist, album, lyrics, cover_data):
    audio = MP3(audio_path)
    audio.tags = ID3()
    audio.tags.add(TIT2(encoding=3, text=title or ''))
    audio.tags.add(TPE1(encoding=3, text=artist or ''))
    audio.tags.add(TALB(encoding=3, text=album or ''))
    if lyrics:
        audio.tags.add(USLT(encoding=3, lang='XXX', desc='Lyrics', text=lyrics))
    if cover_data:
        audio.tags.add(APIC(
            encoding=3,
            mime=_image_mime(cover_data),
            type=3,
            desc='Cover',
            data=cover_data,
        ))
    audio.save(v2_version=3)


def _embed_flac_tags(audio_path, title, artist, album, lyrics, cover_data):
    audio = FLAC(audio_path)
    audio['title'] = title or ''
    audio['artist'] = artist or ''
    audio['album'] = album or ''
    if lyrics:
        audio['lyrics'] = lyrics
    audio.clear_pictures()
    if cover_data:
        picture = Picture()
        picture.data = cover_data
        picture.type = 3
        picture.mime = _image_mime(cover_data)
        picture.desc = 'Cover'
        audio.add_picture(picture)
    audio.save()


def _get_json(url, params):
    response = requests.get(url, params=params, headers=_HEADERS, timeout=10)
    response.raise_for_status()
    return response.json()


def _search_songs(keyword):
    payload = _get_json(f'{_API}/api/search/get', {
        's': keyword,
        'type': 1,
        'limit': 30,
        'offset': 0,
    })
    if payload.get('code') not in (200, None):
        return []
    return (payload.get('result') or {}).get('songs') or []


def _choose_song(songs, title, artist):
    if not songs:
        return None
    title_l = (title or '').lower().strip()
    artist_l = (artist or '').lower().strip()
    # The public search endpoint ranks covers ahead of the original recording.
    noise_markers = ('原唱', '版', 'cover', 'dj', '钢琴', '吉他', '伴奏')
    best = songs[0]
    best_score = None
    for song in songs:
        name = str(song.get('name') or '').strip()
        name_l = name.lower()
        artists = '/'.join(
            artist_info.get('name') or '' for artist_info in song.get('artists') or []
        ).lower()
        score = 0
        if title_l and name_l == title_l:
            score += 5
        elif title_l and (title_l in name_l or name_l in title_l):
            score += 2
        if title_l and name_l != title_l:
            for marker in noise_markers:
                if marker.lower() in name_l and marker.lower() not in title_l:
                    score -= 3
                    break
        if artist_l and artist_l in artists:
            score += 4
        if best_score is None or score > best_score:
            best = song
            best_score = score
    return best


def _names_from_song(song, title, artist):
    title_from_api = song.get('name') or title
    artist_names = [
        artist_info.get('name')
        for artist_info in (song.get('artists') or [])
        if artist_info.get('name')
    ]
    artist_str = '/'.join(artist_names) or artist
    album_str = (song.get('album') or {}).get('name') or ''
    return title_from_api, artist_str, album_str


def _split_filename(filename):
    parts = [part.strip() for part in filename.replace('_', ' ').split('-', 1)]
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[1], parts[0]
    return parts[0], ''


def update_and_embed_metadata(audio_path, title, artist):
    try:
        filename = os.path.splitext(os.path.basename(audio_path))[0]
        if not title or not artist:
            parsed_title, parsed_artist = _split_filename(filename)
            title = title or parsed_title
            artist = artist or parsed_artist

        songs = _search_songs(f'{title} {artist}'.strip())
        song = _choose_song(songs, title, artist)
        if not song or not song.get('id'):
            return

        song_id = song['id']
        title_from_api, artist_str, album_str = _names_from_song(song, title, artist)
        lyrics = None
        cover_data = None
        try:
            lrc_result = _get_json(f'{_API}/api/song/lyric', {'id': song_id, 'lv': 1})
            lyrics = (lrc_result.get('lrc') or {}).get('lyric')
        except Exception:
            pass
        try:
            detail = _get_json(
                f'{_API}/api/song/detail/',
                {'id': song_id, 'ids': f'[{song_id}]'},
            )
            detail_song = (detail.get('songs') or [None])[0]
            if detail_song:
                title_from_api, artist_str, album_str = _names_from_song(
                    detail_song, title_from_api, artist_str
                )
                pic_url = (detail_song.get('album') or {}).get('picUrl')
                if pic_url:
                    response = requests.get(pic_url, headers=_HEADERS, timeout=10)
                    response.raise_for_status()
                    cover_data = response.content
        except Exception:
            pass

        embed_tags(
            audio_path,
            title_from_api,
            artist_str,
            album=album_str,
            lyrics=lyrics,
            cover_data=cover_data,
        )
    except requests.RequestException as exc:
        print(f'在线元数据获取失败，将只播放本地文件: {exc}')
    except Exception:
        traceback.print_exc()
