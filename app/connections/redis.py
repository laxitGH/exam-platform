import redis
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional
from fastapi import FastAPI

from app.utils.config import settings


_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    assert _redis_client is not None, "Redis not initialized"
    return _redis_client


def init_redis() -> None:
    global _redis_client
    _redis_client = redis.Redis(
        db=getattr(settings, "redis_db", 0),
        port=getattr(settings, "redis_port", 6379),
        host=getattr(settings, "redis_host", "localhost"),
        password=getattr(settings, "redis_password", None),
        decode_responses=True,
        socket_timeout=2.0,
    )


def close_redis() -> None:
    global _redis_client
    if _redis_client is not None:
        try:
            _redis_client.close()
        finally:
            _redis_client = None


@asynccontextmanager
async def redis_lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_redis()
    try:
        yield
    finally:
        close_redis()


