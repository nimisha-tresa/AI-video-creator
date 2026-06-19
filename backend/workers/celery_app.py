from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "video_creator",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "workers.tasks.image_gen",
        "workers.tasks.video_gen",
        "workers.tasks.audio_gen",
        "workers.tasks.upscale",
        "workers.tasks.dispatch",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # One task at a time per worker (GPU constraint)
    task_routes={
        "workers.tasks.image_gen.*": {"queue": "image_gen"},
        "workers.tasks.video_gen.*": {"queue": "video_gen"},
        "workers.tasks.upscale.*": {"queue": "upscale"},
        "workers.tasks.dispatch.*": {"queue": "default"},
    },
    task_soft_time_limit=settings.comfyui_timeout + 90,
    task_time_limit=settings.comfyui_timeout + 120,
    result_expires=86400,       # 1 day
)
