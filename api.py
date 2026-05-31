"""
FastAPI server — runs alongside the Discord bot in the same process via asyncio.
Exposes REST endpoints and serves the web UI at /
"""
import os
import json
import asyncio
import hashlib
from contextlib import asynccontextmanager
from datetime import datetime

import discord
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# These are imported from bot.py when running via main.py
# They're declared here as module-level vars that main.py will inject
_bot: discord.Client = None
_player = None
_find_tracks = None
_play_next = None


def init(bot, player, find_tracks, play_next):
    global _bot, _player, _find_tracks, _play_next
    _bot = bot
    _player = player
    _find_tracks = find_tracks
    _play_next = play_next


app = FastAPI(title="MusicBot API")
PLAYER_PASSWORD = os.getenv("PLAYER_PASSWORD", "")
PLAYLISTS_FILE = os.path.join(os.path.dirname(__file__), "playlists.json")
_data_dir = os.getenv("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))
REQUESTS_FILE = os.path.join(_data_dir, "requests.txt")


def load_playlists() -> list:
    if not os.path.exists(PLAYLISTS_FILE):
        return []
    with open(PLAYLISTS_FILE, encoding="utf-8") as f:
        return json.load(f)

# Mount static files for the web UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_voice_client() -> discord.VoiceClient | None:
    if not _bot:
        return None
    for guild in _bot.guilds:
        if guild.voice_client:
            return guild.voice_client
    return None


def get_guild() -> discord.Guild | None:
    if not _bot:
        return None
    for guild in _bot.guilds:
        if guild.voice_client:
            return guild
    return None


# ── Models ────────────────────────────────────────────────────────────────────
class SearchRequest(BaseModel):
    query: str

class VolumeRequest(BaseModel):
    level: int  # 0–100

class QueueAddRequest(BaseModel):
    query: str


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = os.path.join(static_dir, "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse("<h1>MusicBot</h1><p>Static files not found.</p>")


@app.post("/api/auth")
async def auth(req: dict):
    if not PLAYER_PASSWORD:
        return {"ok": True}  # no password set, open access
    return {"ok": req.get("password") == PLAYER_PASSWORD}


@app.get("/api/state")
async def state():
    return _player.to_dict()


@app.post("/api/play")
async def play():
    guild = get_guild()
    vc = get_voice_client()
    if not vc:
        raise HTTPException(status_code=400, detail="Bot is not in a voice channel")
    if vc.is_playing():
        return {"status": "already playing"}
    asyncio.run_coroutine_threadsafe(_play_next(guild), _bot.loop)
    return {"status": "playing"}


@app.post("/api/pause")
async def pause():
    vc = get_voice_client()
    if not vc:
        raise HTTPException(status_code=400, detail="Bot is not in a voice channel")
    if vc.is_paused():
        vc.resume()
        _player.set_paused(False)
        return {"status": "resumed"}
    elif vc.is_playing():
        vc.pause()
        _player.set_paused(True)
        return {"status": "paused"}
    raise HTTPException(status_code=400, detail="Nothing is playing")


@app.post("/api/skip")
async def skip():
    vc = get_voice_client()
    if not vc or not vc.is_playing():
        raise HTTPException(status_code=400, detail="Nothing is playing")
    vc.stop()  # triggers after() → play_next()
    return {"status": "skipped"}


@app.post("/api/stop")
async def stop():
    guild = get_guild()
    vc = get_voice_client()
    if vc:
        _player.clear_queue()
        _player.set_now_playing(None)
        vc.stop()
        asyncio.run_coroutine_threadsafe(vc.disconnect(), _bot.loop)
    return {"status": "stopped"}


@app.post("/api/shuffle")
async def shuffle():
    _player.shuffle_queue()
    return {"status": "shuffled", "queue": _player.get_queue()}


@app.post("/api/loop")
async def toggle_loop():
    is_looping = _player.toggle_loop()
    return {"loop": is_looping}


@app.post("/api/volume")
async def set_volume(req: VolumeRequest):
    if not 0 <= req.level <= 100:
        raise HTTPException(status_code=422, detail="Volume must be 0–100")
    _player.set_volume(req.level / 100)
    vc = get_voice_client()
    if vc and vc.source:
        vc.source.volume = _player.volume
    return {"volume": req.level}


@app.post("/api/queue/add")
async def queue_add(req: QueueAddRequest):
    results = _find_tracks(req.query)
    if not results:
        raise HTTPException(status_code=404, detail=f"No tracks found")
    for t in results:
        _player.add_to_queue(t)
    guild = get_guild()
    vc = get_voice_client()
    if guild and vc and not vc.is_playing():
        asyncio.run_coroutine_threadsafe(_play_next(guild), _bot.loop)
    return {"added": len(results)}


@app.delete("/api/queue")
async def queue_clear():
    _player.clear_queue()
    return {"status": "cleared"}


@app.delete("/api/queue/{index}")
async def queue_remove(index: int):
    removed = _player.remove_from_queue(index)
    if removed is None:
        raise HTTPException(status_code=404, detail="Index out of range")
    return {"removed": os.path.basename(removed)}


@app.get("/api/search")
async def search(q: str = "", limit: int = 200):
    limit = min(limit, 500)
    all_results = _find_tracks(q)
    return {
        "results": [os.path.basename(t) for t in all_results[:limit]],
        "count": min(len(all_results), limit),
        "total": len(all_results),
    }


class TrackRequestBody(BaseModel):
    track: str
    name: str = ""


@app.post("/api/requests")
async def submit_request(req: TrackRequestBody):
    track = req.track.strip()
    if not track:
        raise HTTPException(status_code=422, detail="Track name is required")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    name_part = f" ({req.name.strip()})" if req.name.strip() else ""
    os.makedirs(os.path.dirname(REQUESTS_FILE), exist_ok=True)
    with open(REQUESTS_FILE, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}]{name_part}: {track}\n")
    return {"status": "submitted"}


@app.get("/api/playlists")
async def get_playlists():
    playlists = load_playlists()
    if not playlists:
        return {"playlists": []}
    library_basenames = {os.path.basename(p).lower() for p in _find_tracks(None)}
    result = []
    for pl in playlists:
        tracks = pl.get("tracks", [])
        found = sum(1 for t in tracks if t.lower() in library_basenames)
        result.append({
            "id": pl["id"],
            "name": pl["name"],
            "description": pl.get("description", ""),
            "color": pl.get("color", ""),
            "track_count": len(tracks),
            "found_count": found,
        })
    return {"playlists": result}


@app.post("/api/playlists/{playlist_id}/play")
async def play_playlist(playlist_id: str):
    playlists = load_playlists()
    playlist = next((p for p in playlists if p["id"] == playlist_id), None)
    if not playlist:
        raise HTTPException(status_code=404, detail="Playlist not found")

    library_map = {os.path.basename(p).lower(): p for p in _find_tracks(None)}
    tracks = [library_map[t.lower()] for t in playlist.get("tracks", []) if t.lower() in library_map]

    if not tracks:
        raise HTTPException(status_code=404, detail="No tracks from this playlist found in library")

    guild = get_guild()
    vc = get_voice_client()

    _player.clear_queue()
    _player.set_now_playing(None)
    for t in tracks:
        _player.add_to_queue(t)

    if guild and vc:
        if vc.is_playing() or vc.is_paused():
            vc.stop()  # after() → play_next() will pick up the new queue
        else:
            asyncio.run_coroutine_threadsafe(_play_next(guild), _bot.loop)

    return {"status": "playing", "playlist": playlist["name"], "tracks": len(tracks)}
