"""Shared in-process cache store (TTL dict). Shared across agents in one API process."""

from __future__ import annotations

import copy
import threading
import time
from typing import Any, Optional

_memory_lock = threading.Lock()
_memory_store: dict[str, dict[str, Any]] = {}


def cache_backend() -> str:
    return "memory"


def get_json(key: str) -> Optional[Any]:
    """Return cached value or None if missing/expired."""
    now = time.time()
    with _memory_lock:
        entry = _memory_store.get(key)
        if not entry:
            return None
        if entry.get("expires_at", 0) <= now:
            _memory_store.pop(key, None)
            return None
        return copy.deepcopy(entry.get("value"))


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    ttl = max(1, int(ttl_seconds))
    with _memory_lock:
        _memory_store[key] = {
            "expires_at": time.time() + ttl,
            "value": copy.deepcopy(value),
        }


def delete_key(key: str) -> None:
    with _memory_lock:
        _memory_store.pop(key, None)


def clear_prefix(prefix: str) -> int:
    """Delete keys with the given prefix. Returns count cleared."""
    with _memory_lock:
        to_drop = [k for k in _memory_store if k.startswith(prefix)]
        for k in to_drop:
            _memory_store.pop(k, None)
        return len(to_drop)


def memory_active_count(prefix: str = "") -> int:
    now = time.time()
    with _memory_lock:
        return sum(
            1
            for k, e in _memory_store.items()
            if k.startswith(prefix) and e.get("expires_at", 0) > now
        )


def cache_stats(prefix: str, ttl_seconds: int) -> dict[str, Any]:
    return {
        "backend": "memory",
        "ttl_seconds": ttl_seconds,
        "active_entries": memory_active_count(prefix),
        "prefix": prefix,
    }
