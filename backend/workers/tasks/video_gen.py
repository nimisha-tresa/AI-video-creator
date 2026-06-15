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


def _run_video_generation(generation_id: str, workflow_type: str) -> None:
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
            if workflow_type == "text_to_video":
                workflow = builder.build_animatediff_txt2vid(
                    prompt=gen.prompt or "",
                    negative_prompt=gen.negative_prompt or "",
                    width=gen.width,
                    height=gen.height,
                    num_frames=gen.num_frames,
                    fps=params.get("fps", 8),
                    steps=params.get("steps", 20),
                    cfg=params.get("cfg_scale", 7.0),
                    seed=params.get("seed"),
                    motion_module=params.get("motion_module", "mm_sd_v15_v2.ckpt"),
                    motion_scale=params.get("motion_scale", 1.0),
                    ip_adapter_enabled=params.get("ip_adapter_enabled", False),
                    ip_adapter_scale=params.get("ip_adapter_scale", 0.6),
                )
            else:  # image_to_video
                workflow = builder.build_animatediff_img2vid(
                    prompt=gen.prompt or "",
                    negative_prompt=gen.negative_prompt or "",
                    width=gen.width,
                    height=gen.height,
                    num_frames=gen.num_frames,
                    fps=params.get("fps", 8),
                    steps=params.get("steps", 20),
                    cfg=params.get("cfg_scale", 7.0),
                    denoise=params.get("denoise", 0.85),
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
            seed=result.get("seed"),
        )
        publish_progress(
            owner_id, generation_id,
            {"status": "completed", "progress": 1.0, "output_url": result["url"]}
        )
        logger.info("Video generation completed", id=generation_id, elapsed=gpu_secs)

    except Exception as exc:
        logger.exception("Video generation failed", id=generation_id)
        update_generation_sync(
            generation_id,
            status=GenerationStatus.FAILED,
            error_message=str(exc),
            gpu_seconds=timer.elapsed(),
        )
        publish_progress(owner_id, generation_id, {"status": "failed", "error": str(exc)})
        raise


@celery_app.task(name="workers.tasks.video_gen.text_to_video", bind=True, max_retries=1, queue="video_gen")
def text_to_video(self, generation_id: str):
    _run_video_generation(generation_id, "text_to_video")


@celery_app.task(name="workers.tasks.video_gen.image_to_video", bind=True, max_retries=1, queue="video_gen")
def image_to_video(self, generation_id: str):
    _run_video_generation(generation_id, "image_to_video")
