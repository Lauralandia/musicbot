"""
main.py — starts both the Discord bot and the FastAPI web server in one process.
Run with: python main.py
"""
from dotenv import load_dotenv
load_dotenv()

import asyncio
import os
import threading
import uvicorn

import api
from bot import bot, player, find_tracks, play_next

WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))

# Inject shared state into the API module
api.init(bot, player, find_tracks, play_next)


def run_web():
    """Run FastAPI in a background thread."""
    uvicorn.run(api.app, host=WEB_HOST, port=WEB_PORT, log_level="warning")


if __name__ == "__main__":
    # Start FastAPI in a daemon thread
    web_thread = threading.Thread(target=run_web, daemon=True)
    web_thread.start()
    print(f"Web UI running at http://{WEB_HOST}:{WEB_PORT}")

    # Run the Discord bot (blocks until stopped)
    bot.run(os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE"))
