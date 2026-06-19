from __future__ import annotations

import structlog

from app.models.generation import GenerationStatus
from comfyui.client import ComfyUIClient
from comfyui.workflow_builder import WorkflowBuilder
from workers.celery_app import celery_app
from workers.gpu_manager import gpu_manager
from workers.helpers import Timer, publish_progress, update_generation_sync

logger = structlog.get_logger()


def _run_image_generation(generation_id: str, workflow_type: str) -> None:
    import asyncio

    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.generation import Generation

    timer = Timer()

    async def _get_params():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Generation).where(Generation.id == generation_id)
            )
            return result.scalar_one_or_none()

    gen = asyncio.get_event_loop().run_until_complete(_get_params())
    if not gen:
        logger.error("Generation not found", id=generation_id)
        return

    owner_id = gen.owner_id
    params = gen.params
    extra = params.get("extra", {}) if isinstance(params.get("extra"), dict) else {}

    update_generation_sync(generation_id, status=GenerationStatus.PROCESSING, progress=0.05)
    publish_progress(owner_id, generation_id, {"status": "processing", "progress": 0.05})

    try:
        with gpu_manager.acquire():
            builder = WorkflowBuilder()
            if workflow_type == "text_to_image":
                workflow = builder.build_sdxl_txt2img(
                    prompt=gen.prompt or "",
                    negative_prompt=gen.negative_prompt or "",
                    width=gen.width,
                    height=gen.height,
                    steps=params.get("steps", 30),
                    cfg=params.get("cfg_scale", 7.0),
                    seed=params.get("seed"),
                    sampler=params.get("sampler", "dpmpp_2m"),
                    scheduler=params.get("scheduler", "karras"),
                    ip_adapter_enabled=params.get("ip_adapter_enabled", False),
                    ip_adapter_scale=params.get("ip_adapter_scale", 0.6),
                )
            else:  # image_to_image
                workflow = builder.build_sdxl_img2img(
                    prompt=gen.prompt or "",
                    negative_prompt=gen.negative_prompt or "",
                    width=gen.width,
                    height=gen.height,
                    steps=params.get("steps", 30),
                    cfg=params.get("cfg_scale", 7.0),
                    denoise=params.get("denoise", 0.75),
                )

            workflow = builder.attach_mock_metadata(
                workflow,
                model_id=extra.get("model_id", "flux-2-max"),
                visual_theme=extra.get("visual_theme", "flux"),
                output_kind="image",
            )

            async def _run():
                async with ComfyUIClient() as client:
                    def on_progress(p: float):
                        update_generation_sync(generation_id, progress=p)
                        publish_progress(owner_id, generation_id, {"status": "processing", "progress": p})

                    result = await client.run_workflow(workflow, on_progress=on_progress)
                    return result

            result = asyncio.get_event_loop().run_until_complete(_run())

        gpu_secs = timer.elapsed()
        update_generation_sync(
            generation_id,
            status=GenerationStatus.COMPLETED,
            progress=1.0,
            output_url=result["url"],
            gpu_seconds=gpu_secs,
            seed=result.get("seed"),
        )
        publish_progress(
            owner_id, generation_id,
            {"status": "completed", "progress": 1.0, "output_url": result["url"]}
        )
        logger.info("Image generation completed", id=generation_id, elapsed=gpu_secs)

    except Exception as exc:
        logger.exception("Image generation failed", id=generation_id)
        update_generation_sync(
            generation_id,
            status=GenerationStatus.FAILED,
            error_message=str(exc),
            gpu_seconds=timer.elapsed(),
        )
        publish_progress(owner_id, generation_id, {"status": "failed", "error": str(exc)})
        raise


@celery_app.task(name="workers.tasks.image_gen.text_to_image", bind=True, max_retries=1, queue="image_gen")
def text_to_image(self, generation_id: str):
    _run_image_generation(generation_id, "text_to_image")


@celery_app.task(name="workers.tasks.image_gen.image_to_image", bind=True, max_retries=1, queue="image_gen")
def image_to_image(self, generation_id: str):
    _run_image_generation(generation_id, "image_to_image")
