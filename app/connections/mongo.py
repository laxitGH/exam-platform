from contextlib import asynccontextmanager
from typing import AsyncIterator

import certifi
from fastapi import FastAPI
from mongoengine import connect, disconnect

from app.utils.config import settings


def init_mongo() -> None:
    connect(host=settings.mongo_uri, alias="default", tlsCAFile=certifi.where(), tz_aware=True)


def close_mongo() -> None:
    disconnect(alias="default")


@asynccontextmanager
async def mongo_lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_mongo()
    try:
        yield
    finally:
        close_mongo()
