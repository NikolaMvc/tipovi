"""Thin Redis cache wrapper that degrades to a no-op when Redis is unavailable,
so the API never fails just because the cache is down."""
from __future__ import annotations

import json
from typing import Any, Optional

from backend.config import settings
from backend.scraper.utils import log

_client = None
_checked = False


def _redis():
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    try:
        import redis  # type: ignore
        _client = redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
        _client.ping()
        log.info("Redis cache connected")
    except Exception as exc:  # noqa: BLE001
        log.info("Redis unavailable (%s); caching disabled", exc)
        _client = None
    return _client


def get(key: str) -> Optional[Any]:
    r = _redis()
    if not r:
        return None
    try:
        raw = r.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    r = _redis()
    if not r:
        return
    try:
        r.setex(key, ttl or settings.CACHE_TTL, json.dumps(value, default=str))
    except Exception:
        pass


def invalidate(*keys: str) -> None:
    r = _redis()
    if not r:
        return
    try:
        for k in keys:
            r.delete(k)
    except Exception:
        pass
