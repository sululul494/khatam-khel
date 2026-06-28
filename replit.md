# 🎵 Python Radio Server v2.0

Multi-platform radio broadcasting system with token-based authentication, Icecast streaming, genre-based playlists, and configuration management.

## 🎯 Features

### Radio Server Core
1. **HTTP Streaming** - Direct MP3 audio stream at 128kbps
2. **Icecast Support** - Dual streaming (HTTP + Icecast)
3. **Queue Management** - Dynamic song queue with priority
4. **YouTube Integration** - Downloads with yt-dlp
5. **Live Updates** - Real-time WebSocket events
6. **History Tracking** - Recent songs tracking

### 🆕 New in v2.0

#### Token-Based User Authentication
- **Secure Token Generation** - Admin-controlled user token creation
- **Token Validation** - Middleware for protected endpoints
- **Token Revocation** - Instant token invalidation
- **User Permissions** - Separate admin and user access levels

#### Icecast Streaming Support
- **Dual Streaming** - HTTP + Icecast simultaneously
- **Auto Failover** - Continues with HTTP if Icecast unavailable
- **Status Monitoring** - Real-time connection status
- **Configurable** - All settings via API

#### Genre-Based Playlist Rotation
- **Auto Categorization** - Smart genre detection from filenames
- **Genre Statistics** - Track song distribution by genre
- **Dynamic Rotation** - Play songs based on selected genre
- **Supported Genres**:
  - `all` - All songs (27 songs)
  - `bollywood` - Hindi/Bollywood music (3 songs)
  - `edm` - Electronic dance music (1 song)
  - `pop` - Pop music
  - `rock` - Rock music
  - `chill` - Chill/Lo-fi music
  - `mix` - Mashups and remixes

#### Configuration Management API
- **Dynamic Settings** - Change configuration without restart
- **RESTful API** - GET/POST endpoints
- **Persistent Storage** - JSON-based configuration
- **Admin Protected** - Secure configuration changes

### Highrise Bot
1. **Real-time Updates** - Announces song changes automatically
2. **Interactive Commands** - !np, !queue, !search, !request
3. **Song Requests** - Users request songs from Highrise
4. **Queue Display** - View upcoming songs

## 🚀 Quick Start

### Radio Server

```bash
# Install dependencies
pip install -r requirements.txt

# Set admin credentials (IMPORTANT for production!)
export ADMIN_API_KEY="your-strong-api-key"
export ADMIN_TOKEN_KEY="your-strong-token-key"

# Run server
python radio_app.py
```

**Access:**
- Stream: `http://0.0.0.0:5000/stream`
- API: `http://0.0.0.0:5000/api/`
- Documentation: See `API_DOCS_v2.md`

### Highrise Bot

```bash
# Configure bot_config.py with your credentials
python run_bot.py
```

## 🔐 Security

**⚠️ CRITICAL:** Change default admin credentials before production use!

See `SECURITY.md` for complete security documentation.

**Default Credentials (Development Only):**
- Admin API Key: `admin123`
- Admin Token Key: `token_secret_key`

**To Set Production Credentials:**
1. Go to Replit Secrets
2. Add `ADMIN_API_KEY` with a strong random key
3. Add `ADMIN_TOKEN_KEY` with a strong random key

## 📚 API Documentation

### Authentication Levels

1. **Public** - No authentication required
   - `/stream`, `/api/songs/current`, `/api/songs/queue`, `/api/genres`

2. **User Token** - Requires `x-token-key` header
   - `/api/songs/skip`, `/api/songs/previous`, `/api/songs/add/top`

3. **Admin** - Requires `x-admin-api-key` and `x-admin-token-key` headers
   - `/api/admin/token`, `/api/config`, `/api/genres/scan`

### Quick Examples

```bash
# Generate user token (admin)
curl -X POST http://localhost:5000/api/admin/token \
  -H "x-admin-api-key: admin123" \
  -H "x-admin-token-key: token_secret_key" \
  -d '{"username": "dj_user"}'

# Skip song (user token)
curl -X GET http://localhost:5000/api/songs/skip \
  -H "x-token-key: YOUR_USER_TOKEN"

# Change playlist genre (admin)
curl -X POST http://localhost:5000/api/config \
  -H "x-admin-api-key: admin123" \
  -H "x-admin-token-key: token_secret_key" \
  -d '{"key": "defaultPlaylistGenre", "value": "bollywood"}'

# Get all genres
curl http://localhost:5000/api/genres
```

Complete API documentation: `API_DOCS_v2.md`

## 🎛️ Configuration

Available configuration keys:

| Key | Default | Description |
|-----|---------|-------------|
| `defaultPlaylistGenre` | "all" | Genre for playlist rotation |
| `autoPlaylistRotation` | true | Enable auto-rotation |
| `streamBitrate` | 128 | Audio bitrate (kbps) |
| `enableIcecast` | false | Enable Icecast streaming |
| `icecastHost` | "localhost" | Icecast server host |
| `icecastPort` | 8000 | Icecast server port |
| `icecastPassword` | "hackme" | Icecast source password |

## 📁 Project Structure

```
radio_app.py          # Main server with all features
config_manager.py     # Configuration management
genre_manager.py      # Genre categorization and rotation
icecast_streamer.py   # Icecast streaming support
queue_manager.py      # Queue and playlist management
radio_streamer.py     # Audio playback engine
youtube_dl.py         # YouTube downloader
API_DOCS_v2.md        # Complete API documentation
SECURITY.md           # Security best practices
```

## 🔧 Tech Stack

- **Backend**: Flask + SocketIO
- **Streaming**: FFmpeg (MP3, 128kbps)
- **Download**: yt-dlp
- **Storage**: JSON files
- **Authentication**: Token-based with secure secrets
- **Real-time**: WebSocket events

## 📝 Recent Changes

**October 31, 2025 - v2.0 Major Update**
- ✅ **Token-Based Authentication** - Secure user token system
- ✅ **Icecast Streaming** - Dual HTTP + Icecast streaming
- ✅ **Genre Management** - Auto-categorize and rotate by genre
- ✅ **Configuration API** - Dynamic server configuration
- ✅ **Security Improvements** - Environment-based admin credentials
- ✅ **Code Optimization** - Lightweight, fast, thread-safe
- ✅ **Enhanced Documentation** - Complete API and security docs

**October 30, 2025**
- ✅ Skip button fixed with token authentication
- ✅ FFmpeg watchdog system
- ✅ Auto-restart on stream hang
- ✅ Shuffled default playlist
- ✅ Smart duplicate prevention

**October 29, 2025**
- ✅ Highrise bot integration
- ✅ Real-time broadcast fixes
- ✅ WebSocket improvements

## 🎵 Available Genres

Based on your current song library:
- **All**: 27 songs (complete library)
- **Bollywood**: 3 songs (Hindi music)
- **EDM**: 1 song (Electronic dance)

To scan and update genres:
```bash
curl -X POST http://localhost:5000/api/genres/scan \
  -H "x-admin-api-key: admin123" \
  -H "x-admin-token-key: token_secret_key"
```

## 🎧 Usage Examples

### Listen to Stream
```bash
# VLC
vlc http://0.0.0.0:5000/stream

# mpv
mpv http://0.0.0.0:5000/stream

# Browser
# Just open: http://0.0.0.0:5000/stream
```

### Request a Song
```bash
curl -X POST http://localhost:5000/api/songs/add \
  -H "Content-Type: application/json" \
  -d '{"songName": "Arijit Singh Best", "requestedBy": "Fan"}'
```

### Check Icecast Status
```bash
curl http://localhost:5000/api/icecast/status
```

## 🐛 Troubleshooting

### Stream Not Working
1. Check FFmpeg installation: `which ffmpeg`
2. Verify songs in `songs/` directory
3. Check server logs in workflow console

### Icecast Not Connecting
1. Verify Icecast server is running
2. Check `icecastHost` and `icecastPort` configuration
3. System will fallback to HTTP-only automatically

### Authentication Errors
1. Verify admin credentials are set correctly
2. Check token hasn't been revoked
3. Ensure correct headers are sent

## 📞 Support

For issues or questions:
1. Check `API_DOCS_v2.md` for API details
2. Review `SECURITY.md` for security setup
3. Check workflow logs for errors
4. Review `FIXES_SUMMARY.md` for known fixes

## 🔒 Security Checklist

Before production:
- [ ] Set custom `ADMIN_API_KEY`
- [ ] Set custom `ADMIN_TOKEN_KEY`
- [ ] Change `icecastPassword`
- [ ] Deploy behind HTTPS
- [ ] Configure firewall rules
- [ ] Create user tokens for authorized DJs
- [ ] Review and test token revocation

## User Preferences

- Default playlist genre: `all` (can be changed to bollywood, edm, pop, rock, chill, mix)
- Stream bitrate: 128 kbps
- Auto playlist rotation: Enabled
- Security: Token-based authentication for user actions
