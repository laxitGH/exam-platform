from __future__ import annotations

from typing import Any, Optional

from app.connections.redis import get_redis


def cache_set(key: str, value: str, ttl_seconds: int | None = None) -> bool:
    client = get_redis()
    if ttl_seconds is None:
        return bool(client.set(name=key, value=value))
    return bool(client.setex(name=key, time=ttl_seconds, value=value))


def cache_get(key: str) -> Optional[str]:
    client = get_redis()
    return client.get(name=key)


def cache_delete(key: str) -> int:
    client = get_redis()
    return int(client.delete(key))


