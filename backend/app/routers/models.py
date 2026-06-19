from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.services.model_registry import get_model, list_models

router = APIRouter(prefix="/models", tags=["models"])
settings = get_settings()


def _model_payload(m):
    return {
        "id": m.id,
        "name": m.name,
        "provider": m.provider,
        "category": m.category,
        "generation_type": m.generation_type,
        "description": m.description,
        "badge": m.badge,
        "compatible": m.compatible,
        "pollinations_model": m.pollinations_model,
        "preset": {
            "fps": m.preset.fps,
            "steps": m.preset.steps,
            "cfg": m.preset.cfg,
            "motion_scale": m.preset.motion_scale,
            "visual_theme": m.preset.visual_theme,
            "duration_sec": m.preset.duration_sec,
        },
    }


async def _fetch_comfyui_status() -> dict:
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            resp = await client.get(f"{settings.comfyui_url.rstrip('/')}/status")
            resp.raise_for_status()
            return resp.json()
    except Exception:
        return {}


@router.get("/studio-config")
async def studio_config():
    comfy = await _fetch_comfyui_status()
    engine = comfy.get("engine", "motion-synthesis")
    chain = comfy.get("engine_chain", [])
    pollinations_ready = bool(comfy.get("pollinations_ready"))
    models_ready = bool(comfy.get("models_ready"))
    true_video = bool(comfy.get("true_video")) or engine in (
        "local-animatediff",
        "pollinations-true-video",
    )

    return {
        "true_video_enabled": true_video,
        "video_engine": engine,
        "engine_chain": chain,
        "pollinations_ready": pollinations_ready,
        "models_ready": models_ready,
        "local_engine": engine == "local-animatediff",
        "engine_mode": comfy.get("engine_mode", "auto"),
        "setup_url": "https://enter.pollinations.ai",
        "local_models": comfy.get("local_models", {
            "sd15": "stable-diffusion-v1-5",
            "motion": "animatediff-motion-adapter-v1-5-2",
        }),
    }


@router.get("/")
async def list_studio_models():
    return [_model_payload(m) for m in list_models()]


@router.get("/{model_id}")
async def get_studio_model(model_id: str):
    model = get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return _model_payload(model)
