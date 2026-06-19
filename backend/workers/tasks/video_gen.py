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
    extra = params.get("extra", {}) if isinstance(params.get("extra"), dict) else {}
    source_url = extra.get("source_asset_url")
    fps_val = int(params.get("fps", 12))
    num_frames = gen.num_frames or int(params.get("num_frames", 16))
    duration_sec = float(params.get("source_duration_sec") or max(2.0, num_frames / max(fps_val, 1)))

    logger.info("Generation fetched", id=generation_id, owner_id=owner_id, workflow_type=workflow_type)

    update_generation_sync(generation_id, status=GenerationStatus.PROCESSING, progress=0.05)
    publish_progress(owner_id, generation_id, {"status": "processing", "progress": 0.05})

    # Uploaded video: process the actual file directly — never AI prompt-to-video
    if workflow_type == "video_enhance":
        if not source_url:
            raise ValueError("video_enhance requires an uploaded source video (source_asset_id)")
        from app.services.source_video_processor import process_uploaded_video

        logger.info("Processing uploaded source video directly", id=generation_id, source_url=source_url)
        publish_progress(owner_id, generation_id, {"status": "processing", "progress": 0.4})
        output_url = process_uploaded_video(
            str(source_url),
            width=gen.width or int(params.get("width", 1280)),
            height=gen.height or int(params.get("height", 720)),
            fps=fps_val,
            duration_sec=duration_sec,
        )
        gpu_secs = timer.elapsed()
        update_generation_sync(
            generation_id,
            status=GenerationStatus.COMPLETED,
            progress=1.0,
            output_url=output_url,
            gpu_seconds=gpu_secs,
        )
        publish_progress(
            owner_id, generation_id,
            {"status": "completed", "progress": 1.0, "output_url": output_url},
        )
        logger.info("Source video processing completed", id=generation_id, elapsed=gpu_secs)
        return

    try:
        logger.info("Acquiring GPU slot", id=generation_id)
        with gpu_manager.acquire() as gpu_slot:
            logger.info("GPU slot acquired", id=generation_id, slot=gpu_slot.gpu_id)
            builder = WorkflowBuilder()
            logger.info("Building workflow", id=generation_id, type=workflow_type)

            if workflow_type == "text_to_video":
                # AnimateDiff local model works best at 512px and <=24 frames
                width = min(gen.width or 512, 512)
                height = min(gen.height or 512, 512)
                num_frames = min(gen.num_frames or 16, 24)
                workflow = builder.build_animatediff_txt2vid(
                    prompt=gen.prompt or "",
                    negative_prompt=gen.negative_prompt or "bad quality, blurry, distorted, watermark, text",
                    width=width,
                    height=height,
                    num_frames=num_frames,
                    fps=params.get("fps", 8),
                    steps=params.get("steps", 20),
                    cfg=7.0,
                    seed=params.get("seed"),
                    motion_scale=params.get("motion_scale", 1.0),
                )
            elif workflow_type == "image_to_video":
                workflow = builder.build_animatediff_img2vid(
                    prompt=gen.prompt or "",
                    negative_prompt=gen.negative_prompt or "",
                    width=gen.width,
                    height=gen.height,
                    num_frames=gen.num_frames,
                    fps=params.get("fps", 12),
                    steps=20,
                    cfg=7.0,
                    denoise=0.85,
                )
            elif workflow_type == "video_enhance":
                # VIDEO_ENHANCE: apply prompt-driven style to uploaded video
                workflow = builder.build_video_enhance(
                    prompt=gen.prompt or "",
                    negative_prompt=gen.negative_prompt or "",
                    strength=params.get("strength", 0.8),
                )
            else:
                raise ValueError(f"Unknown workflow type: {workflow_type}")

            extra = params.get("extra", {}) if isinstance(params.get("extra"), dict) else {}
            source_url = extra.get("source_asset_url")
            workflow = builder.attach_mock_metadata(
                workflow,
                model_id=extra.get("model_id", "veo-3.1"),
                visual_theme=extra.get("visual_theme", "default"),
                output_kind="video",
                pollinations_model=extra.get("pollinations_model"),
                source_asset_url=str(source_url) if source_url else None,
                source_asset_type=str(extra.get("source_asset_type")) if extra.get("source_asset_type") else None,
                width=gen.width or int(params.get("width", 1280)),
                height=gen.height or int(params.get("height", 720)),
                fps=fps_val,
                duration_sec=duration_sec,
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


@celery_app.task(name="workers.tasks.video_gen.video_enhance", bind=True, max_retries=1, queue="video_gen")
def video_enhance(self, generation_id: str):
    _run_video_generation(generation_id, "video_enhance")
