from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.generation import Generation, GenerationStatus

settings = get_settings()

_ACTIVE_STATUSES = {
    GenerationStatus.PENDING,
    GenerationStatus.QUEUED,
    GenerationStatus.PROCESSING,
}


def generation_is_stale(generation: Generation, *, now: datetime | None = None) -> bool:
    if generation.status not in _ACTIVE_STATUSES:
        return False
    now = now or datetime.now(timezone.utc)
    updated_at = generation.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    cutoff = now - timedelta(seconds=settings.comfyui_timeout + 60)
    return updated_at < cutoff


async def mark_stale_generations_failed(
    db: AsyncSession,
    generations: list[Generation],
) -> int:
    """Mark stuck generations as failed so the UI stops polling forever."""
    marked = 0
    for generation in generations:
        if not generation_is_stale(generation):
            continue
        generation.status = GenerationStatus.FAILED
        generation.error_message = (
            generation.error_message
            or f"Generation timed out after {settings.comfyui_timeout} seconds with no output."
        )
        marked += 1
    if marked:
        await db.commit()
    return marked
