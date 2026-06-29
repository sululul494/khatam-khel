import json
import threading
from pathlib import Path
from datetime import datetime
import logging
import random

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)


class QueueManager:
    def __init__(self, queue_file="data/queue.json", history_file="data/history.json"):
        self.queue_file = Path(queue_file)
        self.history_file = Path(history_file)
        self.queue_file.parent.mkdir(exist_ok=True)

        self.queue = []
        self.history = []
        self.current_song = None
        self.lock = threading.Lock()
        self.default_playlist = []

        self.load_queue()
        self.load_history()

    def load_queue(self):
        try:
            if self.queue_file.exists():
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                    self.queue = data.get('queue', [])
                    self.current_song = data.get('current_song', None)
                    self.default_playlist = data.get('default_playlist', [])
        except Exception as e:
            logger.error(f"Error loading queue: {e}")
            self.queue = []

    def save_queue(self):
        try:
            with open(self.queue_file, 'w') as f:
                json.dump({
                    'queue': self.queue,
                    'current_song': self.current_song,
                    'default_playlist': self.default_playlist
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving queue: {e}")

    def load_history(self):
        try:
            if self.history_file.exists():
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
        except Exception as e:
            logger.error(f"Error loading history: {e}")
            self.history = []

    def save_history(self):
        try:
            with open(self.history_file, 'w') as f:
                json.dump(self.history[-100:], f, indent=2)
        except Exception as e:
            logger.error(f"Error saving history: {e}")

    def add_to_queue(self, song_info, priority=False, requested_by="Anonymous"):
        with self.lock:
            song_data = {
                'title': song_info.get('title', 'Unknown'),
                'url': song_info.get('url', ''),
                'duration': song_info.get('duration', 0),
                'thumbnail': song_info.get('thumbnail', ''),
                'uploader': song_info.get('uploader', 'Unknown'),
                'requested_by': requested_by,
                'added_at': datetime.now().isoformat(),
                'id': song_info.get('id', '')
            }
            if priority:
                self.queue.insert(0, song_data)
            else:
                self.queue.append(song_data)
            self.save_queue()
            return song_data

    def get_next_song(self):
        with self.lock:
            # Pull from user queue first
            if self.queue:
                song = self.queue.pop(0)
                self.current_song = song
                self.add_to_history(song)
                self.save_queue()
                return song

            # Fall back to default playlist (Auto DJ)
            if self.default_playlist:
                song = self.default_playlist[0].copy()
                song['requested_by'] = 'Auto DJ'
                self.default_playlist = self.default_playlist[1:] + [self.default_playlist[0]]
                self.current_song = song
                self.add_to_history(song)
                self.save_queue()
                return song

            return None

    def get_current_song(self):
        return self.current_song

    def get_queue(self):
        return self.queue.copy()

    def clear_queue(self):
        with self.lock:
            self.queue = []
            self.save_queue()

    def remove_from_queue(self, index):
        with self.lock:
            if 0 <= index < len(self.queue):
                removed = self.queue.pop(index)
                self.save_queue()
                return removed
            return None

    def add_to_history(self, song):
        history_entry = {**song, 'played_at': datetime.now().isoformat()}
        self.history.append(history_entry)
        if len(self.history) > 100:
            self.history = self.history[-100:]
        self.save_history()

    def get_history(self, limit=20):
        return self.history[-limit:][::-1]

    def add_to_default_playlist(self, song_info):
        with self.lock:
            song_data = {
                'title': song_info.get('title', 'Unknown'),
                'url': song_info.get('url', ''),
                'duration': song_info.get('duration', 0),
                'thumbnail': song_info.get('thumbnail', ''),
                'uploader': song_info.get('uploader', 'Unknown'),
                'id': song_info.get('id', '')
            }
            self.default_playlist.append(song_data)
            self.save_queue()
            return song_data

    def get_default_playlist(self):
        return self.default_playlist.copy()

    def clear_default_playlist(self):
        with self.lock:
            self.default_playlist = []
            self.save_queue()

    def get_upcoming_songs(self, limit=10):
        with self.lock:
            upcoming = list(self.queue[:limit])
            remaining = limit - len(upcoming)
            if remaining > 0 and self.default_playlist:
                for i in range(min(remaining, len(self.default_playlist))):
                    song = self.default_playlist[i].copy()
                    song['requested_by'] = 'Auto DJ'
                    song['from_playlist'] = True
                    upcoming.append(song)
            return upcoming

    def has_active_songs(self):
        return bool(self.queue or self.default_playlist)

    def shuffle_playlist(self):
        with self.lock:
            random.shuffle(self.default_playlist)
            self.save_queue()
            return True
