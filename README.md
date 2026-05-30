# MusicBot

Discord music bot + web UI that streams local files from your NAS.

## Discord Developer Portal Setup

This has changed since the early days — here's the current flow:

### 1. Create the application
1. Go to https://discord.com/developers/applications
2. Click **New Application** → give it a name → Create
3. Go to the **Bot** tab in the left sidebar

### 2. Get your token
1. Under the Bot tab, click **Reset Token** → copy it somewhere safe
2. ⚠️ Never commit this to git or share it

### 3. Enable required intents
Still on the Bot tab, scroll to **Privileged Gateway Intents** and enable:
- ✅ **Message Content Intent** — needed to read `!` prefix commands
- ✅ **Server Members Intent** — good practice for voice state tracking

Click **Save Changes**.

### 4. Generate the invite URL
1. Go to **OAuth2** → **URL Generator** in the left sidebar
2. Under **Scopes**, check: `bot` and `applications.commands`
3. Under **Bot Permissions**, check:
   - Connect
   - Speak
   - Use Voice Activity
   - Send Messages
   - Embed Links
   - Read Message History
4. Copy the generated URL at the bottom and paste it in your browser to invite the bot to your server

---

## Unraid Docker Setup

### Environment Variables
| Variable | Value | Description |
|---|---|---|
| `DISCORD_TOKEN` | `your-token-here` | From Discord Developer Portal |
| `MUSIC_DIR` | `/music` | Container path to your music |
| `WEB_PORT` | `8080` | Port for the web UI |

### Path Mapping
| Container Path | Host Path |
|---|---|
| `/music` | `/mnt/user/YourMusicShare` |

### Port Mapping
| Container Port | Host Port |
|---|---|
| `8080` | `8080` (or whatever you prefer) |

### Build & run with docker-compose (for testing)
```bash
cp .env.example .env
# edit .env and add your DISCORD_TOKEN
docker-compose up --build
```

---

## Commands

### Slash commands (type `/` in Discord)
| Command | Description |
|---|---|
| `/join` | Bot joins your voice channel |
| `/play <query>` | Search and play first result immediately |
| `/queue <query>` | Add all results to queue |
| `/skip` | Skip current track |
| `/pause` | Toggle pause/resume |
| `/stop` | Stop and disconnect |
| `/shuffle` | Shuffle the queue |
| `/volume <0-100>` | Set volume |
| `/nowplaying` | Show current track + queue |
| `/search <query>` | Search without playing |

### Web UI
Open `http://YOUR-UNRAID-IP:8080` in any browser.

---

## File Structure
```
musicbot/
├── main.py          # Entrypoint — starts bot + web server together
├── bot.py           # Discord bot, slash commands, FFmpeg playback
├── player.py        # Shared state (queue, now playing, volume)
├── api.py           # FastAPI REST endpoints + static file serving
├── static/
│   └── index.html   # Web UI
├── requirements.txt
├── Dockerfile
└── docker-compose.yml
```

## Supported audio formats
`.mp3` `.flac` `.ogg` `.opus` `.m4a` `.wav` `.aac`
