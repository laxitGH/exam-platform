from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from rq import Queue
from rq_scheduler import Scheduler
from redis import Redis

from app.connections.redis import get_redis


def _redis_conn() -> Redis:
    return get_redis()


def get_scheduler() -> Scheduler:
    return Scheduler(queue_name="scheduler", connection=_redis_conn())


def get_queue() -> Queue:
    return Queue(name="scheduler", connection=_redis_conn())


def schedule_at(run_at: datetime, func: Callable, *args, **kwargs) -> None:
    sched = get_scheduler()
    if run_at.tzinfo is None:
        run_at = run_at.replace(tzinfo=timezone.utc)
    sched.enqueue_at(run_at, func, *args, **kwargs)


