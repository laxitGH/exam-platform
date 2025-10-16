from fastapi import FastAPI
from contextlib import AsyncExitStack

from app.connections import mongo_lifespan
from app.connections.redis import redis_lifespan
from app.api.user import router as user_router
from app.api.test_attempt import router as test_attempt_router
from app.api.exam import router as exam_router


async def combined_lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        await stack.enter_async_context(mongo_lifespan(app))
        await stack.enter_async_context(redis_lifespan(app))

        yield


app = FastAPI(title="Exams Platform (Mongo)", version="0.1.0", lifespan=combined_lifespan)


app.include_router(user_router, prefix="/api/users")
app.include_router(exam_router, prefix="/api/exams")
app.include_router(test_attempt_router, prefix="/api/test-attempts")
