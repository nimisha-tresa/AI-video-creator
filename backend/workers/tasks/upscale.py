from __future__ import annotations

import asyncio

import structlog

from app.models.generation import GenerationStatus
from comfyui.client import ComfyUIClient
from comfyui.workflow_builder import WorkflowBuilder
from workers.celery_app import celery_app
from workers.gpu_manager import gpu_manager
from workers.helpers import Timer, publish_progress, update_generation_sync

logger = structlog.get_logger()


@celery_app.task(name="workers.tasks.upscale.video_upscale", bind=True, max_retries=1, queue="upscale")
def video_upscale(self, generation_id: str):
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.generation import Generation

    timer = Timer()

    async def _get_gen():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Generation).where(Generation.id == generation_id)
            )
            return result.scalar_one_or_none()

    gen = asyncio.get_event_loop().run_until_complete(_get_gen())
    if not gen:
        return

    owner_id = gen.owner_id
    params = gen.params

    update_generation_sync(generation_id, status=GenerationStatus.PROCESSING, progress=0.05)
    publish_progress(owner_id, generation_id, {"status": "processing", "progress": 0.05})

    try:
        with gpu_manager.acquire():
            builder = WorkflowBuilder()
            workflow = builder.build_video_upscale(
                input_url=params.get("input_url", ""),
                scale_factor=params.get("scale_factor", 2),
            )

            async def _run():
                async with ComfyUIClient() as client:
                    def on_progress(p: float):
                        update_generation_sync(generation_id, progress=p)
                        publish_progress(owner_id, generation_id, {"status": "processing", "progress": p})

                    return await client.run_workflow(workflow, on_progress=on_progress)

            result = asyncio.get_event_loop().run_until_complete(_run())

        gpu_secs = timer.elapsed()
        update_generation_sync(
            generation_id,
            status=GenerationStatus.COMPLETED,
            progress=1.0,
            output_url=result["url"],
            gpu_seconds=gpu_secs,
        )
        publish_progress(
            owner_id, generation_id,
            {"status": "completed", "progress": 1.0, "output_url": result["url"]}
        )

    except Exception as exc:
        logger.exception("Upscale failed", id=generation_id)
        update_generation_sync(
            generation_id,
            status=GenerationStatus.FAILED,
            error_message=str(exc),
            gpu_seconds=timer.elapsed(),
        )
        publish_progress(owner_id, generation_id, {"status": "failed", "error": str(exc)})
        raise
