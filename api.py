"""
FastAPI server — runs alongside the Discord bot in the same process via asyncio.
Exposes REST endpoints and serves the web UI at /
"""
import os
import asyncio
import hashlib
from contextlib import asynccontextmanager

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
print(f"DEBUG password is:'{PLAYER_PASSWORD}'")

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
        raise HTTPException(status_code=404, detail=f"No tracks found for: {req.query}")
    for t in results:
        _player.add_to_queue(t)
    guild = get_guild()
    vc = get_voice_client()
    if guild and vc and not vc.is_playing():
        asyncio.run_coroutine_threadsafe(_play_next(guild), _bot.loop)
    return {"added": len(results), "tracks": [os.path.basename(t) for t in results]}


@app.delete("/api/queue/{index}")
async def queue_remove(index: int):
    removed = _player.remove_from_queue(index)
    if removed is None:
        raise HTTPException(status_code=404, detail="Index out of range")
    return {"removed": os.path.basename(removed)}


@app.get("/api/search")
async def search(q: str):
    results = _find_tracks(q)[:20]
    return {"results": [os.path.basename(t) for t in results], "count": len(results)}
