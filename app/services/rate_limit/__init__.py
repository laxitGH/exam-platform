from __future__ import annotations
from fastapi import Depends, HTTPException, Request

from app.connections.redis import get_redis
from app.services.auth import get_current_user
from app.models.user import User


def limit_route(seconds: int):
    """Return a FastAPI dependency that rate-limits a user on a route for N seconds.

    Uses Redis TTL to block repeated calls by the same user to the same path
    within the configured time window.
    """

    def _dependency(request: Request, current_user: User = Depends(get_current_user)) -> None:
        client = get_redis()
        key = f"rl:{current_user.id}:{request.url.path}"

        # If a TTL exists, the user must wait; otherwise set a new TTL.
        ttl = client.ttl(key)
        if ttl and ttl > 0:
            raise HTTPException(status_code=429, detail=f"Rate limited. Try again in {ttl}s")
        client.setex(name=key, time=seconds, value="1")

    return _dependency


