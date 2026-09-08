"""Shared TTL cache store. Two backends, picked by CACHE_BACKEND:

- "memory" (default): in-process dict. Fast, but not shared across instances —
  each Render instance builds up its own cache independently, so scaling to
  more than one instance means a lower effective hit rate per instance, not
  incorrect behavior (this cache is read-through: a miss just re-fetches).
- "postgres": shared table in the existing Neon database. Same TTL semantics,
  but every instance sees the same cache — needed for horizontal scaling to
  actually pay off, since instance N+1 benefits from what instance 1 already
  fetched instead of starting cold. No new infra: reuses DATABASE_URL.
"""

from __future__ import annotations

import copy
import os
import threading
import time
from typing import Any, Optional

from psycopg2.extras import Json

CACHE_BACKEND_NAME = os.environ.get("CACHE_BACKEND", "memory").strip().lower()

_memory_lock = threading.Lock()
_memory_store: dict[str, dict[str, Any]] = {}


def cache_backend() -> str:
    return CACHE_BACKEND_NAME


# ─── memory backend ────────────────────────────────────────────────────────

def _memory_get_json(key: str) -> Optional[Any]:
    now = time.time()
    with _memory_lock:
        entry = _memory_store.get(key)
        if not entry:
            return None
        if entry.get("expires_at", 0) <= now:
            _memory_store.pop(key, None)
            return None
        return copy.deepcopy(entry.get("value"))


def _memory_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    ttl = max(1, int(ttl_seconds))
    with _memory_lock:
        _memory_store[key] = {
            "expires_at": time.time() + ttl,
            "value": copy.deepcopy(value),
        }


def _memory_delete_key(key: str) -> None:
    with _memory_lock:
        _memory_store.pop(key, None)


def _memory_clear_prefix(prefix: str) -> int:
    with _memory_lock:
        to_drop = [k for k in _memory_store if k.startswith(prefix)]
        for k in to_drop:
            _memory_store.pop(k, None)
        return len(to_drop)


def _memory_active_count(prefix: str = "") -> int:
    now = time.time()
    with _memory_lock:
        return sum(
            1
            for k, e in _memory_store.items()
            if k.startswith(prefix) and e.get("expires_at", 0) > now
        )


# ─── postgres backend ──────────────────────────────────────────────────────

def _pg_get_json(key: str) -> Optional[Any]:
    from db import get_conn, init_db

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM cache_kv WHERE key = %s AND expires_at > NOW()",
                (key,),
            )
            row = cur.fetchone()
    # psycopg2 auto-deserializes JSONB columns back to native Python objects.
    return row["value"] if row else None


def _pg_set_json(key: str, value: Any, ttl_seconds: int) -> None:
    from db import get_conn, init_db

    init_db()
    ttl = max(1, int(ttl_seconds))
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cache_kv (key, value, expires_at)
                VALUES (%s, %s, NOW() + (%s || ' seconds')::interval)
                ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at
                """,
                (key, Json(value), ttl),
            )
            # Expired rows are filtered out of reads but otherwise sit forever —
            # opportunistically sweep a small batch on ~1% of writes instead of
            # running a separate cleanup job.
            if os.urandom(1)[0] < 3:  # ~1% of the time
                cur.execute(
                    "DELETE FROM cache_kv WHERE key IN "
                    "(SELECT key FROM cache_kv WHERE expires_at <= NOW() LIMIT 500)"
                )


def _pg_delete_key(key: str) -> None:
    from db import get_conn, init_db

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cache_kv WHERE key = %s", (key,))


def _pg_clear_prefix(prefix: str) -> int:
    from db import get_conn, init_db

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cache_kv WHERE key LIKE %s", (prefix + "%",))
            return cur.rowcount


def _pg_active_count(prefix: str = "") -> int:
    from db import get_conn, init_db

    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS n FROM cache_kv WHERE key LIKE %s AND expires_at > NOW()",
                (prefix + "%",),
            )
            row = cur.fetchone()
    return int(row["n"]) if row else 0


# ─── dispatch ──────────────────────────────────────────────────────────────

def get_json(key: str) -> Optional[Any]:
    """Return cached value or None if missing/expired."""
    if CACHE_BACKEND_NAME == "postgres":
        return _pg_get_json(key)
    return _memory_get_json(key)


def set_json(key: str, value: Any, ttl_seconds: int) -> None:
    if CACHE_BACKEND_NAME == "postgres":
        _pg_set_json(key, value, ttl_seconds)
        return
    _memory_set_json(key, value, ttl_seconds)


def delete_key(key: str) -> None:
    if CACHE_BACKEND_NAME == "postgres":
        _pg_delete_key(key)
        return
    _memory_delete_key(key)


def clear_prefix(prefix: str) -> int:
    """Delete keys with the given prefix. Returns count cleared."""
    if CACHE_BACKEND_NAME == "postgres":
        return _pg_clear_prefix(prefix)
    return _memory_clear_prefix(prefix)


def memory_active_count(prefix: str = "") -> int:
    if CACHE_BACKEND_NAME == "postgres":
        return _pg_active_count(prefix)
    return _memory_active_count(prefix)


def cache_stats(prefix: str, ttl_seconds: int) -> dict[str, Any]:
    return {
        "backend": CACHE_BACKEND_NAME,
        "ttl_seconds": ttl_seconds,
        "active_entries": memory_active_count(prefix),
        "prefix": prefix,
    }
