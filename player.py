import random
import threading
from collections import deque


class MusicPlayer:
    """
    Shared player state. Both the Discord bot and the FastAPI server
    read/write this object so controls stay in sync across both interfaces.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._queue: deque[str] = deque()
        self._now_playing: str | None = None
        self._paused: bool = False
        self._volume: float = 0.5  # 0.0 – 1.0
        self._loop: bool = False

    # ── Queue ──────────────────────────────────────────────────────────────
    def add_to_queue(self, track: str) -> str:
        with self._lock:
            self._queue.append(track)
        return track

    def next_track(self) -> str | None:
        with self._lock:
            if self._loop and self._now_playing:
                # Re-insert current track at front before popping
                self._queue.appendleft(self._now_playing)
            return self._queue.popleft() if self._queue else None

    def toggle_loop(self) -> bool:
        with self._lock:
            self._loop = not self._loop
            return self._loop

    def clear_queue(self):
        with self._lock:
            self._queue.clear()

    def shuffle_queue(self):
        with self._lock:
            items = list(self._queue)
            random.shuffle(items)
            self._queue = deque(items)

    def get_queue(self) -> list[str]:
        with self._lock:
            return list(self._queue)

    def remove_from_queue(self, index: int) -> str | None:
        with self._lock:
            items = list(self._queue)
            if 0 <= index < len(items):
                removed = items.pop(index)
                self._queue = deque(items)
                return removed
        return None

    # ── State ──────────────────────────────────────────────────────────────
    def set_now_playing(self, track: str | None):
        with self._lock:
            self._now_playing = track

    def set_paused(self, paused: bool):
        with self._lock:
            self._paused = paused

    def set_volume(self, volume: float):
        with self._lock:
            self._volume = max(0.0, min(1.0, volume))

    # ── Properties ─────────────────────────────────────────────────────────
    @property
    def now_playing(self) -> str | None:
        return self._now_playing

    @property
    def loop(self) -> bool:
        return self._loop

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def volume(self) -> float:
        return self._volume

    def to_dict(self) -> dict:
        """Serialise state for the web API."""
        import os
        queue = self.get_queue()
        return {
            "now_playing": os.path.basename(self._now_playing) if self._now_playing else None,
            "now_playing_path": self._now_playing,
            "paused": self._paused,
            "loop": self._loop,
            "volume": int(self._volume * 100),
            "queue": [os.path.basename(t) for t in queue],
            "queue_count": len(queue),
        }