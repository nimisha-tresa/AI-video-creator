from __future__ import annotations

import structlog

from app.models.generation import GenerationStatus
from comfyui.client import ComfyUIClient
from comfyui.workflow_builder import WorkflowBuilder
from workers.celery_app import celery_app
from workers.gpu_manager import gpu_manager
from workers.helpers import Timer, publish_progress, update_generation_sync

logger = structlog.get_logger()


def _run_audio_generation(generation_id: str) -> None:
    import asyncio

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.generation import Generation

    timer = Timer()

    async def _get_gen():
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(Generation).where(Generation.id == generation_id))
            return result.scalar_one_or_none()

    gen = asyncio.get_event_loop().run_until_complete(_get_gen())
    if not gen:
        raise ValueError(f"Generation {generation_id} not found")

    owner_id = gen.owner_id
    params = gen.params
    extra = params.get("extra", {}) if isinstance(params.get("extra"), dict) else {}
    model_id = extra.get("model_id", "eleven-v3")
    theme = extra.get("visual_theme", "eleven")

    update_generation_sync(generation_id, status=GenerationStatus.PROCESSING, progress=0.05)
    publish_progress(owner_id, generation_id, {"status": "processing", "progress": 0.05})

    try:
        with gpu_manager.acquire():
            builder = WorkflowBuilder()
            workflow = builder.build_mock_audio(
                prompt=gen.prompt or "",
                model_id=model_id,
                visual_theme=theme,
            )

            async def _run():
                async with ComfyUIClient() as client:
                    def on_progress(p: float):
                        update_generation_sync(generation_id, progress=p)
                        publish_progress(owner_id, generation_id, {"status": "processing", "progress": p})

                    return await client.run_workflow(workflow, on_progress=on_progress)

            result = asyncio.get_event_loop().run_until_complete(_run())

        update_generation_sync(
            generation_id,
            status=GenerationStatus.COMPLETED,
            progress=1.0,
            output_url=result["url"],
            gpu_seconds=timer.elapsed(),
        )
        publish_progress(owner_id, generation_id, {"status": "completed", "progress": 1.0, "output_url": result["url"]})
        logger.info("Audio generation completed", id=generation_id)

    except Exception as exc:
        logger.exception("Audio generation failed", id=generation_id)
        update_generation_sync(generation_id, status=GenerationStatus.FAILED, error_message=str(exc), gpu_seconds=timer.elapsed())
        publish_progress(owner_id, generation_id, {"status": "failed", "error": str(exc)})
        raise


@celery_app.task(name="workers.tasks.audio_gen.text_to_audio", bind=True, max_retries=1, queue="default")
def text_to_audio(self, generation_id: str):
    _run_audio_generation(generation_id)
