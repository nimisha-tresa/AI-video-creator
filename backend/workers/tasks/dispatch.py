from __future__ import annotations

import structlog

from app.models.generation import GenerationStatus, GenerationType
from workers.celery_app import celery_app

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.dispatch.dispatch_generation", bind=True, max_retries=0)
def dispatch_generation(self, generation_id: str):
    """Route a generation to the correct specialist task."""
    import asyncio

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.generation import Generation

    async def _get_type() -> tuple[GenerationType, str]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Generation.type, Generation.owner_id).where(Generation.id == generation_id)
            )
            row = result.one_or_none()
            if not row:
                raise ValueError(f"Generation {generation_id} not found")
            return row

    gen_type, owner_id = asyncio.get_event_loop().run_until_complete(_get_type())

    route_map = {
        GenerationType.TEXT_TO_VIDEO: "workers.tasks.video_gen.text_to_video",
        GenerationType.IMAGE_TO_VIDEO: "workers.tasks.video_gen.image_to_video",
        GenerationType.VIDEO_ENHANCE: "workers.tasks.video_gen.video_enhance",
        GenerationType.TEXT_TO_IMAGE: "workers.tasks.image_gen.text_to_image",
        GenerationType.IMAGE_TO_IMAGE: "workers.tasks.image_gen.image_to_image",
        GenerationType.TEXT_TO_AUDIO: "workers.tasks.audio_gen.text_to_audio",
    }

    task_name = route_map.get(gen_type)
    if not task_name:
        raise ValueError(f"Unknown generation type: {gen_type}")

    celery_app.send_task(task_name, args=[generation_id])
    logger.info("Dispatched generation", id=generation_id, type=gen_type, task=task_name)
