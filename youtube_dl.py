import yt_dlp
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

COOKIES_FILE = Path(__file__).parent / "cookies.txt"


def _base_opts(extra: dict = None) -> dict:
    """Base yt-dlp options, with cookies injected if cookies.txt exists."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb'],
            }
        },
        'sleep_interval_requests': 2,
        'sleep_interval': 1,
        'max_sleep_interval': 5,
    }
    if COOKIES_FILE.exists():
        opts['cookiefile'] = str(COOKIES_FILE)
        logger.info(f"Using cookies from {COOKIES_FILE}")
    if extra:
        opts.update(extra)
    return opts


class YouTubeDownloader:
    def __init__(self, download_dir="songs"):
        pass

    def cookies_loaded(self) -> bool:
        return COOKIES_FILE.exists()

    def get_video_info(self, url):
        """Get video metadata only (no download, no stream URL)."""
        try:
            opts = _base_opts({
                'extract_flat': False,
                'skip_download': True,
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    'title': info.get('title', 'Unknown'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Unknown'),
                    'url': url,
                    'id': info.get('id', ''),
                    'file_path': ''
                }
        except Exception as e:
            logger.error(f"Video info error: {e}")
            return None

    def get_playlist_songs(self, playlist_url):
        """Fetch all entries from a YouTube playlist (metadata only)."""
        try:
            opts = _base_opts({
                'extract_flat': True,
                'ignoreerrors': True,
            })
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(playlist_url, download=False)
                songs = []
                for entry in result.get('entries', []):
                    if entry and entry.get('id'):
                        songs.append({
                            'title': entry.get('title', 'Unknown'),
                            'url': f"https://www.youtube.com/watch?v={entry['id']}",
                            'duration': entry.get('duration', 180),
                            'thumbnail': entry.get('thumbnail', ''),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'id': entry['id'],
                            'file_path': ''
                        })
                return songs
        except Exception as e:
            logger.error(f"Playlist fetch error: {e}")
            return []

    def search_youtube(self, query, max_results=5):
        """Search YouTube and return video metadata."""
        try:
            opts = _base_opts({'extract_flat': True})
            with yt_dlp.YoutubeDL(opts) as ydl:
                results = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
                videos = []
                for entry in results.get('entries', []):
                    if entry:
                        videos.append({
                            'title': entry.get('title', 'Unknown'),
                            'url': f"https://www.youtube.com/watch?v={entry.get('id', '')}",
                            'duration': entry.get('duration', 0),
                            'thumbnail': entry.get('thumbnail', ''),
                            'uploader': entry.get('uploader', 'Unknown'),
                            'id': entry.get('id', ''),
                            'file_path': ''
                        })
                return videos
        except Exception as e:
            logger.error(f"Search error: {e}")
            return []
