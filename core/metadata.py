import os
import shutil
import traceback
import requests
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, USLT, TIT2, TPE1, TALB
from pyncm.apis import cloudsearch, track

# The ncmdump script is in the same directory, so a direct import should work
# when the app is run from the project root.
from core import ncmdump


def get_song_metadata(song_path):
    try:
        audio = MP3(song_path, ID3=ID3)
        tag = audio.tags
        
        metadata = {
            "path": song_path,
            "title": str(tag.get('TIT2', [os.path.basename(song_path).rsplit('.', 1)[0]])[0]),
            "artist": str(tag.get('TPE1', ['未知艺术家'])[0]),
            "duration": audio.info.length,
            "lyrics": None,
            "cover_pixmap": None
        }

        for key in tag.keys():
            if key.startswith('USLT'):
                metadata['lyrics'] = tag[key].text
                break

        # This part requires Qt, so we handle it in the main UI thread after loading
        # for key in tag.keys():
        #     if key.startswith('APIC:'):
        #         img_data = tag[key].data
        #         pixmap = QPixmap()
        #         pixmap.loadFromData(img_data)
        #         metadata['cover_pixmap'] = pixmap.scaled(200, 200, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        #         break
        
        return metadata
    except Exception as e:
        traceback.print_exc()
        return None

def get_cover_data_from_tags(song_path):
    try:
        audio = MP3(song_path, ID3=ID3)
        tag = audio.tags
        for key in tag.keys():
            if key.startswith('APIC:'):
                return tag[key].data
    except Exception:
        return None
    return None

def convert_ncm_to_mp3(ncm_path):
    source_dir = os.path.dirname(ncm_path)
    output_dir = 'output'
    if not os.path.exists(output_dir): os.makedirs(output_dir)

    original_cwd = os.getcwd()
    try:
        # ncmdump seems to work best when run from the file's directory
        if source_dir: os.chdir(source_dir)
        ncmdump.dump(os.path.basename(ncm_path))
    except Exception:
        traceback.print_exc()
        return None
    finally:
        os.chdir(original_cwd)

    mp3_file = os.path.basename(ncm_path).replace('.ncm', '.mp3')
    original_converted_path = os.path.join(source_dir, mp3_file)

    if os.path.exists(original_converted_path):
        destination_path = os.path.join(output_dir, os.path.basename(original_converted_path))
        try:
            shutil.move(original_converted_path, destination_path)
        except shutil.Error: # File might already exist
            os.remove(original_converted_path)
        return destination_path
    return None

def update_and_embed_metadata(mp3_path, title, artist):
    try:
        filename = os.path.basename(mp3_path).rsplit('.', 1)[0]
        if not title or not artist: # If empty, use filename
            # A more robust split for filenames like "Artist - Title"
            parts = [p.strip() for p in filename.replace('_', ' ').split('-', 1)]
            if len(parts) == 2:
                artist, title = parts
            else:
                title = parts[0]
                artist = ""

        search_result = cloudsearch.GetSearchResult(keyword=f"{title} {artist}", limit=1)
        songs = search_result.get('result', {}).get('songs')
        if not songs: return
        
        song_info = songs[0]
        song_id = song_info.get('id')
        if not song_id: return
        
        title_from_api = song_info.get('name', title)
        artist_str = '/'.join(a['name'] for a in song_info.get('ar', [])) or artist
        album_str = song_info.get('al', {}).get('name', '')
        
        lyrics = None
        try:
            lrc_result = track.GetTrackLyrics(song_id)
            lyrics = lrc_result.get('lrc', {}).get('lyric')
        except Exception: pass

        cover_data = None
        try:
            track_detail = track.GetTrackDetail(song_id)
            pic_url = track_detail['songs'][0]['al']['picUrl']
            if pic_url:
                response = requests.get(pic_url, timeout=10)
                response.raise_for_status()
                cover_data = response.content
        except Exception: pass
            
        audio = MP3(mp3_path)
        try:
            audio.delete()
        except: pass
        audio.tags = ID3()
        audio.tags.add(TIT2(encoding=3, text=title_from_api))
        audio.tags.add(TPE1(encoding=3, text=artist_str))
        audio.tags.add(TALB(encoding=3, text=album_str))
        if lyrics:
            audio.tags.add(USLT(encoding=3, lang='XXX', desc='Lyrics', text=lyrics))
        if cover_data:
            audio.tags.add(APIC(encoding=3, mime='image/jpeg', type=3, desc='Cover', data=cover_data))
        
        audio.save(v2_version=3)
    except Exception as e:
        traceback.print_exc() 