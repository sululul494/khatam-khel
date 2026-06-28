# Radio Server — API Documentation

**Base URL:** `http://your-domain:5000`  
**Stream URL:** `http://your-domain:5000/stream`

> Direct streaming mode — songs play straight from YouTube via FFmpeg. No downloads, no local storage.

---

## Authentication

| Level | Header(s) Required |
|-------|--------------------|
| Public | None |
| User Token | `x-token-key: <token>` |
| Admin | `x-admin-api-key: <key>` + `x-admin-token-key: <key>` |

Default admin credentials (override with env vars `ADMIN_API_KEY` and `ADMIN_TOKEN_KEY`):
- `x-admin-api-key: admin123`
- `x-admin-token-key: token_secret_key`

---

## Public Endpoints

### `GET /`
Server info.

**Response:**
```json
{
  "stream": "/stream",
  "current": "/api/songs/current",
  "queue": "/api/songs/queue",
  "auto_dj": "active",
  "playlist": "https://youtube.com/playlist?list=..."
}
```

---

### `GET /stream`
Live MP3 audio stream at 128kbps. Open in any media player or browser.

```bash
vlc http://your-domain:5000/stream
mpv http://your-domain:5000/stream
```

---

### `GET /api/songs/current`
Currently playing song.

**Response:**
```json
{
  "title": "Dominic Fike - Babydoll",
  "uploader": "Lyrics",
  "duration": 210,
  "thumbnail": "https://...",
  "url": "https://youtube.com/watch?v=...",
  "requested_by": "Auto DJ"
}
```

---

### `GET /api/songs/upcoming`
Next song in queue.

**Response:** Same shape as `/api/songs/current`

---

### `GET /api/songs/queue`
Full queue and currently playing song.

**Response:**
```json
{
  "current": { "title": "...", "url": "...", "duration": 210 },
  "queue": [
    { "title": "...", "url": "...", "requested_by": "Fan" }
  ]
}
```

---

### `GET /api/songs/history?limit=20`
Recently played songs, newest first.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | integer | 20 | How many songs to return (max 100) |

**Response:**
```json
{
  "history": [
    { "title": "...", "url": "...", "played_at": "2025-01-01T12:00:00" }
  ]
}
```

---

### `POST /api/songs/add`
Search YouTube by name and add to queue. Streams directly — no download.

**Body:**
```json
{
  "songName": "Tum Hi Ho Arijit Singh",
  "requestedBy": "Fan123"
}
```

**Response:**
```json
{
  "success": true,
  "song": {
    "title": "Tum Hi Ho",
    "url": "https://youtube.com/watch?v=...",
    "duration": 261
  }
}
```

---

### `POST /api/request`
Add a song by direct YouTube URL. Streams directly — no download.

**Body:**
```json
{
  "url": "https://youtube.com/watch?v=VIDEO_ID",
  "requested_by": "Fan123",
  "priority": false
}
```

**Response:**
```json
{
  "success": true,
  "song": { "title": "Song Title", "url": "..." }
}
```

---

### `GET /api/cookies/status`
Check whether YouTube cookies are loaded.

**Response:**
```json
{
  "cookies_loaded": true,
  "file": "/home/runner/workspace/radio/cookies.txt",
  "size_bytes": 478197,
  "message": "Cookies active — YouTube streaming enabled"
}
```

---

### `GET /api/autodj/status`
Shows Auto DJ playlist info and first 20 loaded songs.

**Response:**
```json
{
  "playlist_url": "https://youtube.com/playlist?list=...",
  "total_songs": 100,
  "songs": [
    { "title": "Dominic Fike - Babydoll", "url": "https://..." }
  ],
  "showing": "first 20 of 100"
}
```

---

## User Endpoints (Token Required)

All require header: `x-token-key: <your_token>`

---

### `GET /api/songs/skip`
Skip the current song.

```bash
curl -H "x-token-key: YOUR_TOKEN" http://your-domain:5000/api/songs/skip
```

**Response:**
```json
{
  "success": true,
  "next_song": { "title": "Next Song Title" }
}
```

---

### `GET /api/songs/previous`
Jump back to the previous song.

**Response:**
```json
{
  "success": true,
  "song": { "title": "Previous Song Title" }
}
```

---

### `POST /api/songs/add/top`
Add a song to the **top** of the queue (plays next).

**Body:**
```json
{
  "songName": "Shape of You Ed Sheeran",
  "requestedBy": "DJ"
}
```

**Response:**
```json
{
  "success": true,
  "song": { "title": "Shape of You", "url": "..." }
}
```

---

### `DELETE /api/songs/remove/<index>`
Remove a song from the queue by position (0-based).

```bash
curl -X DELETE -H "x-token-key: YOUR_TOKEN" \
  http://your-domain:5000/api/songs/remove/0
```

**Response:**
```json
{
  "success": true,
  "removed": { "title": "Removed Song Title" }
}
```

---

## Admin Endpoints

All require: `x-admin-api-key` + `x-admin-token-key` headers.

---

### `POST /api/admin/token`
Create a new user token.

**Body:**
```json
{ "username": "dj_user" }
```

**Response:**
```json
{
  "token": "abc123xyz...",
  "username": "dj_user"
}
```

---

### `GET /api/admin/tokens/list`
List all active tokens (previewed, not full values).

**Response:**
```json
{
  "tokens": [
    {
      "token_preview": "abc12345...wxyz",
      "username": "dj_user",
      "created_at": "2025-01-01T12:00:00"
    }
  ]
}
```

---

### `DELETE /api/admin/tokens/revoke`
Revoke a user token.

**Body:**
```json
{ "token": "full_token_string" }
```

**Response:**
```json
{ "success": true, "message": "Token revoked" }
```

---

### `GET /api/config`
Get current server config.

**Response:**
```json
{
  "auto_dj_playlist": "https://youtube.com/playlist?list=...",
  "stream_bitrate": 128,
  "admin_api_key_set": false,
  "admin_token_key_set": false
}
```

---

### `POST /api/admin/autodj/refresh`
Reload the playlist from YouTube (re-fetches all metadata).

**Response:**
```json
{ "success": true, "message": "Auto DJ refresh started" }
```

---

### `POST /api/admin/autodj/shuffle`
Shuffle the Auto DJ playlist order.

**Response:**
```json
{ "success": true, "message": "Playlist shuffled" }
```

---

## WebSocket Events

Connect using Socket.IO to `ws://your-domain:5000`.

### Server → Client:

| Event | Payload | Description |
|-------|---------|-------------|
| `connected` | `{ current, queue }` | On connection |
| `now_playing` | `{ song, queue }` | When a new song starts |
| `queue_update` | `{ queue }` | When queue changes |
| `song_skipped` | `{ next }` | When a song is skipped |
| `playlist_loaded` | `{ count, playlist }` | When Auto DJ finishes loading |

### Client → Server:

| Event | Description |
|-------|-------------|
| `ping` | Heartbeat — server replies with `pong` |

**Example (JavaScript):**
```javascript
const socket = io('http://your-domain:5000');

socket.on('connected', (data) => {
  console.log('Now playing:', data.current?.title);
});

socket.on('now_playing', (data) => {
  console.log('Playing:', data.song.title);
});

socket.on('playlist_loaded', (data) => {
  console.log(`Auto DJ loaded ${data.count} songs`);
});
```

---

## Error Responses

| Status | Meaning |
|--------|---------|
| `400` | Missing required field |
| `401` | Invalid or missing token / admin credentials |
| `404` | Song or resource not found |
| `500` | Internal server error |

**Format:**
```json
{ "error": "Description of the error" }
```

---

## Quick Examples

```bash
# Listen to stream
vlc http://your-domain:5000/stream

# What's playing?
curl http://your-domain:5000/api/songs/current

# Request a song by name (no auth)
curl -X POST http://your-domain:5000/api/songs/add \
  -H "Content-Type: application/json" \
  -d '{"songName": "Tum Hi Ho", "requestedBy": "Fan"}'

# Request by URL (no auth)
curl -X POST http://your-domain:5000/api/request \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=VIDEO_ID"}'

# Create user token (admin)
curl -X POST http://your-domain:5000/api/admin/token \
  -H "x-admin-api-key: admin123" \
  -H "x-admin-token-key: token_secret_key" \
  -H "Content-Type: application/json" \
  -d '{"username": "dj_user"}'

# Skip song (user token)
curl -H "x-token-key: YOUR_TOKEN" http://your-domain:5000/api/songs/skip

# Check Auto DJ status
curl http://your-domain:5000/api/autodj/status

# Shuffle Auto DJ playlist (admin)
curl -X POST http://your-domain:5000/api/admin/autodj/shuffle \
  -H "x-admin-api-key: admin123" \
  -H "x-admin-token-key: token_secret_key"
```
