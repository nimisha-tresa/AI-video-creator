"""Remove prior generations and local output files for a user."""

from __future__ import annotations

import structlog
from pathlib import Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.generation import Generation

logger = structlog.get_logger()
settings = get_settings()


def _unlink_local_output(output_url: str | None) -> None:
    if not output_url:
        return
    marker = "/local_outputs/"
    if marker not in output_url:
        return
    filename = output_url.rsplit(marker, 1)[-1].split("?")[0].strip()
    if not filename or ".." in filename or "/" in filename or "\\" in filename:
        return
    path = Path(settings.local_output_dir) / filename
    try:
        if path.is_file():
            path.unlink()
            logger.info("Deleted local output file", path=str(path))
    except OSError as exc:
        logger.warning("Failed to delete local output", path=str(path), error=str(exc))


async def clear_user_generations(db: AsyncSession, user_id: str) -> int:
    """Delete all generations for a user and remove linked local output files."""
    result = await db.execute(select(Generation).where(Generation.owner_id == user_id))
    generations = list(result.scalars().all())
    for gen in generations:
        _unlink_local_output(gen.output_url)
        _unlink_local_output(gen.thumbnail_url)
        await db.delete(gen)
    if generations:
        await db.flush()
        logger.info("Cleared prior generations", user_id=user_id, count=len(generations))
    return len(generations)
