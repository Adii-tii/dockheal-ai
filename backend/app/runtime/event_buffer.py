"""
Rolling in-memory buffer for Docker events.

The docker event listener writes every raw event here.
The context aggregator reads from here — no need to re-query
the Docker daemon for historical events.

Thread-safe: uses a deque with maxlen, protected by a Lock.
"""

import threading
from collections import deque
from datetime import datetime, timezone

_lock = threading.Lock()
_buffer: deque = deque(maxlen=500)   # last 500 events across all containers


def push(event: dict) -> None:
    """Append a raw Docker event dict to the buffer."""
    # Enrich with a Python-native timestamp for easy filtering
    event = dict(event)
    event["_received_at"] = datetime.now(timezone.utc).isoformat()
    with _lock:
        _buffer.append(event)


def get_for_container(container_name: str, limit: int = 20) -> list[dict]:
    """
    Return up to `limit` most-recent events for a specific container,
    newest first.
    """
    with _lock:
        snapshot = list(_buffer)

    filtered = [
        e for e in snapshot
        if e.get("Actor", {}).get("Attributes", {}).get("name") == container_name
    ]

    # Reverse so newest is first, then slice
    return list(reversed(filtered))[:limit]


def get_all(limit: int = 100) -> list[dict]:
    """Return up to `limit` most-recent events across all containers."""
    with _lock:
        snapshot = list(_buffer)
    return list(reversed(snapshot))[:limit]
