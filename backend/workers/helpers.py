from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Any

import redis
import structlog

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.generation import Generation, GenerationStatus

settings = get_settings()
logger = structlog.get_logger()


def get_sync_redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def publish_progress(user_id: str, generation_id: str, payload: dict) -> None:
    """Push a progress update to the user's WebSocket channel via Redis pub/sub."""
    import json

    r = get_sync_redis()
    message = json.dumps({"type": "generation_update", "data": {"id": generation_id, **payload}})
    r.publish(f"user:{user_id}:generations", message)


def update_generation_sync(
    generation_id: str,
    *,
    status: GenerationStatus | None = None,
    progress: float | None = None,
    output_url: str | None = None,
    error_message: str | None = None,
    gpu_seconds: float | None = None,
    seed: int | None = None,
) -> None:
    """Synchronous DB update called from within a Celery task."""

    async def _update():
        async with AsyncSessionLocal() as session:
            from sqlalchemy import select

            result = await session.execute(
                select(Generation).where(Generation.id == generation_id)
            )
            gen = result.scalar_one_or_none()
            if not gen:
                return None

            if status is not None:
                gen.status = status
            if progress is not None:
                gen.progress = progress
            if output_url is not None:
                gen.output_url = output_url
            if error_message is not None:
                gen.error_message = error_message
            if gpu_seconds is not None:
                gen.gpu_seconds = gpu_seconds
            if seed is not None:
                gen.seed = seed

            await session.commit()
            return gen.owner_id

    return asyncio.get_event_loop().run_until_complete(_update())


class Timer:
    def __init__(self):
        self._start = time.perf_counter()

    def elapsed(self) -> float:
        return time.perf_counter() - self._start
