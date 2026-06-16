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
    logger.info("Starting video generation", id=generation_id, type=workflow_type)

    async def _get_gen():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Generation).where(Generation.id == generation_id)
            )
            return result.scalar_one_or_none()

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    try:
        gen = loop.run_until_complete(_get_gen())
    except Exception as e:
        logger.error("Failed to fetch generation from DB", id=generation_id, error=str(e))
        raise

    if not gen:
        logger.error("Generation not found", id=generation_id)
        raise ValueError(f"Generation {generation_id} not found")

    owner_id = gen.owner_id
    params = gen.params
    logger.info("Generation fetched", id=generation_id, owner_id=owner_id)

    update_generation_sync(generation_id, status=GenerationStatus.PROCESSING, progress=0.05)
    publish_progress(owner_id, generation_id, {"status": "processing", "progress": 0.05})

    try:
        logger.info("Acquiring GPU slot", id=generation_id)
        with gpu_manager.acquire() as gpu_slot:
            logger.info("GPU slot acquired", id=generation_id, slot=gpu_slot.gpu_id)
            builder = WorkflowBuilder()
            logger.info("Building workflow", id=generation_id, type=workflow_type, prompt_len=len(gen.prompt or ""))

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

            logger.info("Submitting to ComfyUI", id=generation_id, url="http://localhost:8188")

            async def _run():
                async with ComfyUIClient() as client:
                    def on_progress(p: float):
                        logger.debug("Generation progress", id=generation_id, progress=p)
                        update_generation_sync(generation_id, progress=p)
                        publish_progress(owner_id, generation_id, {"status": "processing", "progress": p})

                    return await client.run_workflow(workflow, on_progress=on_progress)

            try:
                result = loop.run_until_complete(_run())
                logger.info("Workflow completed", id=generation_id, has_url=bool(result.get("url")))
            except Exception as e:
                logger.error("Workflow execution failed", id=generation_id, error=str(e))
                raise

        gpu_secs = timer.elapsed()
        output_url = result.get("url")
        if not output_url:
            raise ValueError("ComfyUI did not return an output URL")

        logger.info("Updating DB with completion", id=generation_id, url_len=len(output_url))
        update_generation_sync(
            generation_id,
            status=GenerationStatus.COMPLETED,
            progress=1.0,
            output_url=output_url,
            gpu_seconds=gpu_secs,
            seed=result.get("seed"),
        )
        publish_progress(
            owner_id, generation_id,
            {"status": "completed", "progress": 1.0, "output_url": output_url}
        )
        logger.info("Video generation completed successfully", id=generation_id, elapsed=gpu_secs)

    except Exception as exc:
        logger.exception("Video generation failed", id=generation_id, error_type=type(exc).__name__)
        error_msg = f"{type(exc).__name__}: {str(exc)}"
        try:
            update_generation_sync(
                generation_id,
                status=GenerationStatus.FAILED,
                error_message=error_msg,
                gpu_seconds=timer.elapsed(),
            )
            publish_progress(owner_id, generation_id, {"status": "failed", "error": error_msg})
        except Exception as db_exc:
            logger.error("Failed to update DB with error", id=generation_id, db_error=str(db_exc))
        raise


@celery_app.task(name="workers.tasks.video_gen.text_to_video", bind=True, max_retries=1, queue="video_gen")
def text_to_video(self, generation_id: str):
    _run_video_generation(generation_id, "text_to_video")


@celery_app.task(name="workers.tasks.video_gen.image_to_video", bind=True, max_retries=1, queue="video_gen")
def image_to_video(self, generation_id: str):
    _run_video_generation(generation_id, "image_to_video")
