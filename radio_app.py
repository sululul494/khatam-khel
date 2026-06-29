from flask import Flask, request, jsonify, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS
from typing import Optional, Dict, Any
import threading
import time
import subprocess
import traceback
import sys
from pathlib import Path
from collections import deque
from queue import Queue, Empty
import os
import json
import secrets
from datetime import datetime
import select

from youtube_dl import YouTubeDownloader, COOKIES_FILE
from queue_manager import QueueManager

# ==================== SETUP ====================

AUTO_DJ_PLAYLIST = "https://youtube.com/playlist?list=PLDIoUOhQQPlXzhp-83rECoLaV6BwFtNC4"

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_urlsafe(32)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

yt_downloader = YouTubeDownloader()
queue_manager = QueueManager()

ADMIN_API_KEY = os.getenv('ADMIN_API_KEY', 'admin123')
ADMIN_TOKEN_KEY = os.getenv('ADMIN_TOKEN_KEY', 'token_secret_key')

if ADMIN_API_KEY == 'admin123' or ADMIN_TOKEN_KEY == 'token_secret_key':
    print("⚠️  WARNING: Using default admin credentials!")

TOKENS_FILE = Path("data/tokens.json")
tokens_lock = threading.Lock()
token_cache = {}
token_cache_lock = threading.Lock()

# Streaming state
CHUNK_SIZE = 4096
BITRATE_BPS = 128 * 1024          # 128kbps in bits
BYTES_PER_SEC = BITRATE_BPS // 8  # 16384 bytes/sec
CHUNK_INTERVAL = CHUNK_SIZE / BYTES_PER_SEC  # ~0.25 sec per chunk

stream_buffer: deque = deque(maxlen=200)
stream_lock = threading.Lock()
stream_clients: list = []
current_ffmpeg: Optional[subprocess.Popen] = None
ffmpeg_lock = threading.Lock()
skip_event = threading.Event()
stream_running = False


# ==================== AUTH HELPERS ====================

def broadcast_update(event_type: str, data: Dict[str, Any]):
    socketio.emit(event_type, data)


def load_tokens() -> Dict[str, Any]:
    global token_cache
    with token_cache_lock:
        if token_cache:
            return token_cache.copy()
        try:
            if TOKENS_FILE.exists():
                with open(TOKENS_FILE, 'r') as f:
                    token_cache = json.load(f)
                    return token_cache.copy()
        except Exception as e:
            print(f"Error loading tokens: {e}")
        return {}


def save_tokens(tokens: Dict[str, Any]):
    global token_cache
    try:
        TOKENS_FILE.parent.mkdir(exist_ok=True)
        with open(TOKENS_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        with token_cache_lock:
            token_cache = tokens.copy()
    except Exception as e:
        print(f"Error saving tokens: {e}")


def generate_token(username: str = "") -> str:
    token = secrets.token_urlsafe(32)
    with tokens_lock:
        tokens = load_tokens()
        tokens[token] = {
            'username': username or f"User-{len(tokens) + 1}",
            'created_at': datetime.now().isoformat(),
        }
        save_tokens(tokens)
    return token


def validate_token(token: str) -> bool:
    with tokens_lock:
        return token in load_tokens()


def validate_admin(api_key: str, token_key: str) -> bool:
    return api_key == ADMIN_API_KEY and token_key == ADMIN_TOKEN_KEY


def revoke_token(token: str) -> bool:
    with tokens_lock:
        tokens = load_tokens()
        if token in tokens:
            del tokens[token]
            save_tokens(tokens)
            return True
    return False


def require_token(func):
    def wrapper(*args, **kwargs):
        token = request.headers.get('x-token-key', '')
        if not token and request.is_json:
            token = (request.get_json() or {}).get('token', '')
        if not validate_token(token):
            return jsonify({'error': 'Invalid or missing token'}), 401
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def require_admin(func):
    def wrapper(*args, **kwargs):
        api_key = request.headers.get('x-admin-api-key', '')
        token_key = request.headers.get('x-admin-token-key', '')
        if not validate_admin(api_key, token_key):
            return jsonify({'error': 'Invalid admin credentials'}), 401
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


# ==================== DIRECT STREAMING CORE ====================

def distribute_chunk(chunk: bytes):
    """Send an audio chunk to all connected HTTP clients"""
    with stream_lock:
        stream_buffer.append(chunk)
        dead = []
        for client_q in stream_clients:
            try:
                client_q.put_nowait(chunk)
            except Exception:
                dead.append(client_q)
        for d in dead:
            if d in stream_clients:
                stream_clients.remove(d)


def kill_proc(proc):
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def stream_song(song: Dict[str, Any]) -> bool:
    """Stream one song by piping yt-dlp → FFmpeg → HTTP clients."""
    global current_ffmpeg

    url = song.get('url', '')
    if not url:
        print("❌ No URL provided for song")
        return False

    title = song.get('title', 'Unknown')
    print(f"▶️  Streaming: {title}")

    broadcast_update('now_playing', {
        'song': queue_manager.get_current_song(),
        'queue': queue_manager.get_queue()
    })

    # Build yt-dlp command — inject cookies if available
    ydlp_cmd = [
        'yt-dlp',
        '--quiet',
        '--no-warnings',
        '--format', 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio',
        '--extractor-args', 'youtube:player_client=android_vr',
        '--output', '-',
    ]
    if COOKIES_FILE.exists():
        ydlp_cmd += ['--cookies', str(COOKIES_FILE)]
        print(f"🍪 Using cookies for: {title}")
    else:
        print("⚠️  No cookies.txt found — YouTube may block this request")

    ydlp_cmd.append(url)

    ydlp_proc = None
    ffmpeg_proc = None

    try:
        # yt-dlp downloads audio and writes raw audio bytes to stdout
        ydlp_proc = subprocess.Popen(
            ydlp_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )

        # FFmpeg reads from yt-dlp's stdout and encodes to MP3
        ffmpeg_proc = subprocess.Popen([
            'ffmpeg',
            '-i', 'pipe:0',
            '-vn',
            '-c:a', 'libmp3lame',
            '-b:a', '128k',
            '-f', 'mp3',
            '-'
        ], stdin=ydlp_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Let ydlp_proc receive SIGPIPE when ffmpeg closes stdin
        ydlp_proc.stdout.close()

        with ffmpeg_lock:
            current_ffmpeg = ffmpeg_proc

        skip_event.clear()
        last_data = time.time()
        chunk_deadline = time.time()
        ffmpeg_startup_timeout = 30.0  # Wait up to 30s for FFmpeg to start producing data
        ffmpeg_started = False
        consecutive_empty_reads = 0
        max_empty_reads = 10  # Allow up to 10 consecutive empty reads before giving up

        while stream_running:
            # Check for skip event
            if skip_event.is_set():
                print(f"⏭  Skip requested for: {title}")
                return False

            # Check if FFmpeg has exited unexpectedly
            ffmpeg_poll = ffmpeg_proc.poll()
            if ffmpeg_poll is not None:
                # FFmpeg process ended - check if it had a chance to produce data
                if not ffmpeg_started:
                    print(f"❌ FFmpeg exited early (code {ffmpeg_poll}) before producing data")
                    # Try to read stderr for error info
                    try:
                        stderr_data = ffmpeg_proc.stderr.read().decode(errors='replace').strip()
                        if stderr_data:
                            print(f"FFmpeg stderr: {stderr_data[:500]}")
                    except Exception:
                        pass
                else:
                    print(f"✅ FFmpeg finished normally for: {title}")
                break

            # Check for timeout on data
            if time.time() - last_data > 60:
                print(f"⚠️  No data for 60s, skipping: {title}")
                return False

            # Wait for data from FFmpeg with a longer timeout
            ready, _, _ = select.select([ffmpeg_proc.stdout], [], [], 1.0)
            if not ready:
                # No data ready - check if we're still in startup phase
                if not ffmpeg_started and time.time() - chunk_deadline > ffmpeg_startup_timeout:
                    print(f"❌ FFmpeg startup timeout ({ffmpeg_startup_timeout}s) - no data produced")
                    return False
                continue

            # Read chunk
            chunk = ffmpeg_proc.stdout.read(CHUNK_SIZE)
            if not chunk:
                consecutive_empty_reads += 1
                if consecutive_empty_reads >= max_empty_reads:
                    print(f"❌ Too many consecutive empty reads ({max_empty_reads}), stopping")
                    return False
                # Small delay before retrying
                time.sleep(0.1)
                continue

            # Successfully got data
            consecutive_empty_reads = 0

            if not ffmpeg_started:
                ffmpeg_started = True
                print(f"✅ FFmpeg started producing data for: {title}")

            last_data = time.time()
            distribute_chunk(chunk)

            # Advance deadline for real-time pacing
            chunk_deadline += CHUNK_INTERVAL
            if chunk_deadline < time.time() - 2.0:
                chunk_deadline = time.time()

        # Wait for processes to fully terminate
        try:
            if ydlp_proc and ydlp_proc.poll() is None:
                ydlp_proc.terminate()
                ydlp_proc.wait(timeout=5)
        except Exception:
            try:
                if ydlp_proc:
                    ydlp_proc.kill()
            except Exception:
                pass

        try:
            if ffmpeg_proc and ffmpeg_proc.poll() is None:
                ffmpeg_proc.terminate()
                ffmpeg_proc.wait(timeout=5)
        except Exception:
            try:
                if ffmpeg_proc:
                    ffmpeg_proc.kill()
            except Exception:
                pass

    except Exception as e:
        print(f"❌ Error streaming {title}: {e}")
        traceback.print_exc(file=sys.stdout)
        return False
    finally:
        # Ensure cleanup
        try:
            if ydlp_proc and ydlp_proc.poll() is None:
                ydlp_proc.kill()
        except Exception:
            pass
        try:
            if ffmpeg_proc and ffmpeg_proc.poll() is None:
                ffmpeg_proc.kill()
        except Exception:
            pass

    # Log errors and check for rate limiting
    rate_limited = False
    try:
        if ydlp_proc and ydlp_proc.stderr:
            ydlp_err = ydlp_proc.stderr.read().decode(errors='replace').strip()
            if ydlp_err:
                print(f"⚠️  yt-dlp stderr [{title}]: {ydlp_err[:500]}")
                if 'rate-limit' in ydlp_err.lower() or 'rate limit' in ydlp_err.lower() or '429' in ydlp_err:
                    rate_limited = True
        if ffmpeg_proc and ffmpeg_proc.stderr:
            ffmpeg_err = ffmpeg_proc.stderr.read().decode(errors='replace').strip()
            if ffmpeg_err and 'error' in ffmpeg_err.lower():
                print(f"⚠️  ffmpeg stderr [{title}]: {ffmpeg_err[:200]}")
    except Exception:
        pass

    with ffmpeg_lock:
        current_ffmpeg = None

    if rate_limited:
        print(f"🚦 Rate-limited by YouTube — backing off 60s before next song")
        time.sleep(60)
        return False

    print(f"✅ Finished: {title}")
    return True


def stream_manager():
    """Main loop: continuously picks next song and streams it directly"""
    global stream_running
    stream_running = True
    print("📻 Stream manager started", flush=True)

    consecutive_errors = 0
    max_consecutive_errors = 5

    try:
        while stream_running:
            try:
                # Check if skip was requested
                if skip_event.is_set():
                    skip_event.clear()
                    print("⏭  Skip event cleared, moving to next song")

                song = queue_manager.get_next_song()

                if not song:
                    print("⏸  Queue empty, waiting...", flush=True)
                    time.sleep(5)
                    continue

                result = stream_song(song)

                if result:
                    consecutive_errors = 0
                    # Brief pause between songs to let clients settle
                    time.sleep(1)
                else:
                    consecutive_errors += 1
                    print(f"⚠️  Song failed ({consecutive_errors}/{max_consecutive_errors} consecutive failures)", flush=True)

                    # If too many consecutive failures, take a break
                    if consecutive_errors >= max_consecutive_errors:
                        print(f"🚨 Too many consecutive failures, pausing for 30 seconds")
                        time.sleep(30)
                        consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                print(f"❌ Stream error: {e}", flush=True)
                traceback.print_exc(file=sys.stdout)
                sys.stdout.flush()
                time.sleep(10)

                if consecutive_errors >= max_consecutive_errors:
                    print(f"🚨 Too many consecutive errors, pausing for 30 seconds")
                    time.sleep(30)
                    consecutive_errors = 0

    except BaseException as e:
        print(f"💀 Stream manager crashed: {e}", flush=True)
        traceback.print_exc(file=sys.stdout)
        sys.stdout.flush()
        # Try to restart the stream manager
        print("🔄 Attempting to restart stream manager...")
        time.sleep(5)
        stream_manager()


# ==================== AUTO DJ ====================

def auto_dj_load():
    """Fetch playlist metadata and populate default playlist (no downloads)"""
    print(f"🎧 Auto DJ: Loading playlist metadata...")
    songs = yt_downloader.get_playlist_songs(AUTO_DJ_PLAYLIST)

    if not songs:
        print("❌ Auto DJ: Could not fetch playlist")
        return

    print(f"🎧 Auto DJ: {len(songs)} songs loaded into rotation")
    queue_manager.clear_default_playlist()
    for song in songs:
        queue_manager.add_to_default_playlist(song)

    broadcast_update('playlist_loaded', {
        'count': len(songs),
        'playlist': AUTO_DJ_PLAYLIST
    })
    print("✅ Auto DJ ready!")


# ==================== PUBLIC ENDPOINTS ====================

@app.route('/')
def index():
    return jsonify({
        'stream': '/stream',
        'current': '/api/songs/current',
        'queue': '/api/songs/queue',
        'auto_dj': 'active',
        'playlist': AUTO_DJ_PLAYLIST
    })


@app.route('/stream')
def stream():
    """Live HTTP MP3 stream"""
    def generate():
        client_q: Queue = Queue(maxsize=200)
        # Grab the latest buffered chunks so new listeners get a short warm‑up
        with stream_lock:
            for chunk in list(stream_buffer)[-10:]:
                try:
                    client_q.put_nowait(chunk)
                except Exception:
                    pass
            stream_clients.append(client_q)
        try:
            while True:
                try:
                    # Increased timeout to 30 s – Railway’s dynos may pause briefly
                    chunk = client_q.get(timeout=30)
                    if chunk:
                        yield chunk
                except Empty:
                    # No data received – send a silent placeholder to keep the connection alive
                    # This avoids the client seeing a premature EOF while the next song is booting
                    yield b''
                except Exception as e:
                    # Log unexpected errors but keep the generator alive
                    print(f"⚠️ Stream generator error: {e}")
                    traceback.print_exc(file=sys.stdout)
                    yield b''
        finally:
            # Clean up client registration when the connection finishes
            with stream_lock:
                if client_q in stream_clients:
                    stream_clients.remove(client_q)

    return Response(
        generate(),
        mimetype='audio/mpeg',
        headers={
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'X-Content-Type-Options': 'nosniff'
        }
    )


@app.route('/api/songs/current', methods=['GET'])
def get_current_song():
    return jsonify(queue_manager.get_current_song() or {})


@app.route('/api/songs/upcoming', methods=['GET'])
def get_upcoming():
    upcoming = queue_manager.get_upcoming_songs(1)
    return jsonify(upcoming[0] if upcoming else {})


@app.route('/api/songs/queue', methods=['GET'])
def get_queue():
    return jsonify({
        'queue': queue_manager.get_queue(),
        'current': queue_manager.get_current_song()
    })


@app.route('/api/songs/history', methods=['GET'])
def get_history():
    limit = int(request.args.get('limit', 20))
    return jsonify({'history': queue_manager.get_history(limit)})


@app.route('/api/songs/add', methods=['POST'])
def add_song():
    """Search YouTube and add to queue — streams directly, no download"""
    data = request.get_json() or {}
    song_name = data.get('songName', '')
    requested_by = data.get('requestedBy', 'Anonymous')

    if not song_name:
        return jsonify({'error': 'songName required'}), 400

    results = yt_downloader.search_youtube(song_name, max_results=1)
    if not results:
        return jsonify({'error': 'Song not found'}), 404

    song = queue_manager.add_to_queue(results[0], requested_by=requested_by)
    broadcast_update('queue_update', {'queue': queue_manager.get_queue()})
    return jsonify({'success': True, 'song': song})


@app.route('/api/request', methods=['POST'])
def request_song():
    """Add a song by direct YouTube URL — streams directly"""
    data = request.get_json() or {}
    url = data.get('url', '')
    requested_by = data.get('requested_by', 'Anonymous')
    priority = data.get('priority', False)

    if not url:
        return jsonify({'error': 'url required'}), 400

    info = yt_downloader.get_video_info(url)
    if not info:
        return jsonify({'error': 'Invalid URL or video not found'}), 404

    song = queue_manager.add_to_queue(info, priority=priority, requested_by=requested_by)
    broadcast_update('queue_update', {'queue': queue_manager.get_queue()})
    return jsonify({'success': True, 'song': song})


@app.route('/api/cookies/status', methods=['GET'])
def cookies_status():
    exists = COOKIES_FILE.exists()
    size = COOKIES_FILE.stat().st_size if exists else 0
    return jsonify({
        'cookies_loaded': exists,
        'file': str(COOKIES_FILE),
        'size_bytes': size,
        'message': 'Cookies active — YouTube streaming enabled' if exists else 'No cookies.txt found. Upload cookies.txt to the radio/ folder.'
    })


@app.route('/api/autodj/status', methods=['GET'])
def autodj_status():
    playlist = queue_manager.get_default_playlist()
    return jsonify({
        'playlist_url': AUTO_DJ_PLAYLIST,
        'total_songs': len(playlist),
        'songs': [{'title': s['title'], 'url': s['url']} for s in playlist[:20]],
        'showing': f"first 20 of {len(playlist)}"
    })


# ==================== USER ENDPOINTS ====================

@app.route('/api/songs/skip', methods=['GET', 'POST'])
@require_token
def skip_song():
    upcoming = queue_manager.get_upcoming_songs(1)
    next_song = upcoming[0] if upcoming else None
    skip_event.set()
    broadcast_update('song_skipped', {'next': next_song})
    return jsonify({'success': True, 'next_song': next_song})


@app.route('/api/songs/previous', methods=['GET', 'POST'])
@require_token
def previous_song():
    history = queue_manager.get_history(2)
    if len(history) >= 2:
        prev = history[1]
        queue_manager.add_to_queue(prev, priority=True, requested_by='Previous')
        skip_event.set()
        return jsonify({'success': True, 'song': prev})
    return jsonify({'error': 'No previous song'}), 404


@app.route('/api/songs/add/top', methods=['POST'])
@require_token
def add_song_top():
    data = request.get_json() or {}
    song_name = data.get('songName', '')
    requested_by = data.get('requestedBy', 'User')

    if not song_name:
        return jsonify({'error': 'songName required'}), 400

    results = yt_downloader.search_youtube(song_name, max_results=1)
    if not results:
        return jsonify({'error': 'Song not found'}), 404

    song = queue_manager.add_to_queue(results[0], priority=True, requested_by=requested_by)
    broadcast_update('queue_update', {'queue': queue_manager.get_queue()})
    return jsonify({'success': True, 'song': song})


@app.route('/api/songs/remove/<int:index>', methods=['DELETE'])
@require_token
def remove_song(index):
    removed = queue_manager.remove_from_queue(index)
    if removed:
        broadcast_update('queue_update', {'queue': queue_manager.get_queue()})
        return jsonify({'success': True, 'removed': removed})
    return jsonify({'error': 'Invalid index'}), 400


# ==================== ADMIN ENDPOINTS ====================

@app.route('/api/admin/token', methods=['POST'])
@require_admin
def create_token():
    data = request.get_json() or {}
    username = data.get('username', '')
    token = generate_token(username)
    return jsonify({'token': token, 'username': username})


@app.route('/api/admin/tokens/list', methods=['GET'])
@require_admin
def list_tokens():
    with tokens_lock:
        tokens = load_tokens()
        token_list = [
            {
                'token_preview': t[:8] + '...' + t[-4:],
                'username': info['username'],
                'created_at': info['created_at']
            }
            for t, info in tokens.items()
        ]
    return jsonify({'tokens': token_list})


@app.route('/api/admin/tokens/revoke', methods=['DELETE'])
@require_admin
def revoke_token_endpoint():
    data = request.get_json() or {}
    token = data.get('token', '')
    if revoke_token(token):
        return jsonify({'success': True, 'message': 'Token revoked'})
    return jsonify({'error': 'Token not found'}), 404


@app.route('/api/config', methods=['GET'])
@require_admin
def get_config():
    return jsonify({
        'auto_dj_playlist': AUTO_DJ_PLAYLIST,
        'stream_bitrate': 128,
        'admin_api_key_set': ADMIN_API_KEY != 'admin123',
        'admin_token_key_set': ADMIN_TOKEN_KEY != 'token_secret_key'
    })


@app.route('/api/admin/autodj/refresh', methods=['POST'])
@require_admin
def refresh_autodj():
    threading.Thread(target=auto_dj_load, daemon=True).start()
    return jsonify({'success': True, 'message': 'Auto DJ refresh started'})


@app.route('/api/admin/autodj/shuffle', methods=['POST'])
@require_admin
def shuffle_autodj():
    queue_manager.shuffle_playlist()
    return jsonify({'success': True, 'message': 'Playlist shuffled'})


# ==================== WEBSOCKET ====================

@socketio.on('connect')
def handle_connect():
    emit('connected', {
        'current': queue_manager.get_current_song(),
        'queue': queue_manager.get_queue()
    })


@socketio.on('disconnect')
def handle_disconnect():
    pass


@socketio.on('ping')
def handle_ping():
    emit('pong')


# ==================== START ====================

def start_services():
    print("🎵 Starting Radio Server...")

    # Load Auto DJ playlist in background (just metadata fetch)
    threading.Thread(target=auto_dj_load, daemon=True).start()

    # Start the main stream loop
    threading.Thread(target=stream_manager, daemon=True).start()

    print("✅ Radio Server ready")
    print(f"🎧 Auto DJ Playlist: {AUTO_DJ_PLAYLIST}")


if __name__ == '__main__':
    print("=" * 50)
    print("🎵 Radio Server — Direct Streaming Mode")
    print("=" * 50)
    print(f"Stream:  http://0.0.0.0:5000/stream")
    print(f"API:     http://0.0.0.0:5000/api/")
    print("=" * 50)

    start_services()
    port = int(os.getenv('PORT', 5000))
    socketio.run(
        app,
        host='0.0.0.0',
        port=port,
        debug=False,
        allow_unsafe_werkzeug=True,
        use_reloader=False,
        log_output=False
    )
