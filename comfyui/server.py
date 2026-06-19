#!/usr/bin/env python3
"""ComfyUI-compatible server — local AnimateDiff models + optional Pollinations fallback."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from aiohttp import web

from download_models import models_ready
from prompt_engine import (
    generate_prompt_audio,
    generate_prompt_image,
    generate_prompt_video,
    generate_video_from_source,
    true_video_enabled,
)

logger = logging.getLogger(__name__)

ENGINE_MODE = os.environ.get("COMFYUI_ENGINE", "auto").strip().lower()
AUTO_DOWNLOAD = os.environ.get("AUTO_DOWNLOAD_MODELS", "false").lower() in ("1", "true", "yes")
OUTPUT_DIR = Path("/app/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SESSIONS: dict[str, dict] = {}
PROMPT_META: dict[str, dict] = {}
OUTPUT_CACHE: dict[str, tuple[bytes, str]] = {}
EXECUTOR = ThreadPoolExecutor(max_workers=1)


def active_engine() -> str:
    """Primary engine that will be tried first."""
    if ENGINE_MODE == "pollinations" and true_video_enabled():
        return "pollinations"
    if ENGINE_MODE == "local" and models_ready():
        return "local"
    if ENGINE_MODE == "auto":
        if true_video_enabled():
            return "pollinations"
        if models_ready():
            return "local"
    elif true_video_enabled():
        return "pollinations"
    elif models_ready():
        return "local"
    return "fallback"


def engine_chain() -> list[str]:
    """Ordered fallback chain for auto mode."""
    chain: list[str] = []
    if true_video_enabled() and ENGINE_MODE in ("auto", "pollinations"):
        chain.append("pollinations")
    if models_ready() and ENGINE_MODE in ("auto", "local"):
        chain.append("local")
    if "fallback" not in chain:
        chain.append("fallback")
    return chain or ["fallback"]


def _extract_from_workflow(workflow: dict) -> dict:
    prompt = ""
    negative = ""
    model_id = "animatediff-local"
    theme = "default"
    pollinations_model = ""
    width, height = 512, 512
    output_kind = "video"
    duration = 4.0
    fps = 8
    num_frames = 16
    steps = 20
    seed = None

    source_asset_url = ""
    source_asset_type = ""

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        ctype = node.get("class_type", "")
        inputs = node.get("inputs", {})

        if ctype == "CLIPTextEncode":
            text = inputs.get("text", "")
            if text and "bad quality" not in text.lower() and "blurry" not in text.lower():
                if not prompt:
                    prompt = text
            else:
                negative = text
        elif ctype == "MockModelInfo":
            model_id = inputs.get("model_id", model_id)
            theme = inputs.get("visual_theme", theme)
            output_kind = inputs.get("output_kind", output_kind)
            pollinations_model = inputs.get("pollinations_model", pollinations_model)
            source_asset_url = inputs.get("source_asset_url", source_asset_url) or source_asset_url
            source_asset_type = inputs.get("source_asset_type", source_asset_type) or source_asset_type
            if inputs.get("width"):
                width = int(inputs["width"])
            if inputs.get("height"):
                height = int(inputs["height"])
            if inputs.get("fps"):
                fps = int(inputs["fps"])
            if inputs.get("duration_sec"):
                duration = float(inputs["duration_sec"])
        elif ctype == "EmptyLatentImage":
            width = int(inputs.get("width", width))
            height = int(inputs.get("height", height))
            num_frames = int(inputs.get("batch_size", num_frames))
            duration = max(2.0, min(num_frames / max(fps, 1), 12.0))
        elif ctype == "KSampler":
            steps = int(inputs.get("steps", steps))
            if inputs.get("seed") is not None:
                seed = int(inputs["seed"])
        elif ctype == "SaveImage":
            output_kind = "image"
        elif ctype == "ADE_AnimateDiffCombine":
            fps = int(inputs.get("frame_rate", fps))
            output_kind = "video"

    return {
        "prompt": prompt,
        "negative_prompt": negative,
        "model_id": model_id,
        "pollinations_model": pollinations_model,
        "theme": theme,
        "width": width,
        "height": height,
        "output_kind": output_kind,
        "duration": duration,
        "fps": fps,
        "num_frames": num_frames,
        "steps": steps,
        "seed": seed,
        "source_asset_url": source_asset_url,
        "source_asset_type": source_asset_type,
    }


def _run_local(meta: dict, progress_cb) -> tuple[Path, str]:
    from local_engine import generate_image, generate_video

    kind = meta.get("output_kind", "video")
    if kind == "image":
        path = generate_image(
            meta.get("prompt", ""),
            negative_prompt=meta.get("negative_prompt", ""),
            width=int(meta.get("width", 512)),
            height=int(meta.get("height", 512)),
            steps=int(meta.get("steps", 25)),
            seed=meta.get("seed"),
            on_progress=progress_cb,
        )
        return path, "image/png"

    path = generate_video(
        meta.get("prompt", ""),
        negative_prompt=meta.get("negative_prompt", ""),
        width=int(meta.get("width", 512)),
        height=int(meta.get("height", 512)),
        num_frames=int(meta.get("num_frames", 16)),
        fps=int(meta.get("fps", 8)),
        steps=int(meta.get("steps", 20)),
        seed=meta.get("seed"),
        on_progress=progress_cb,
    )
    return path, "video/mp4"


async def _run_pollinations(meta: dict) -> tuple[Path, str]:
    prompt = meta.get("prompt", "")
    w = int(meta.get("width", 512))
    h = int(meta.get("height", 512))
    kind = meta.get("output_kind", "video")
    duration = float(meta.get("duration", 4.0))
    seed = meta.get("seed")

    if kind == "image":
        path = await generate_prompt_image(prompt, w, h, seed=seed)
        return path, "image/png"
    if kind == "audio":
        path = await generate_prompt_audio(prompt, duration=min(duration, 6.0))
        return path, "audio/mpeg"

    path = await generate_prompt_video(
        prompt, w, h,
        duration=duration,
        fps=int(meta.get("fps", 24)),
        seed=seed,
        model_id=meta.get("model_id"),
        pollinations_model=meta.get("pollinations_model"),
        allow_motion_fallback=False,
    )
    return path, "video/mp4"


async def _resolve_output(meta: dict, progress_cb=None) -> tuple[bytes, str]:
    kind = meta.get("output_kind", "video")
    source_url = (meta.get("source_asset_url") or "").strip()
    source_type = (meta.get("source_asset_type") or "").strip()

    if source_url and kind == "video":
        logger.info("Generating from uploaded source asset type=%s", source_type or "video")
        path = await generate_video_from_source(
            source_url,
            meta.get("prompt", ""),
            width=int(meta.get("width", 512)),
            height=int(meta.get("height", 512)),
            duration=float(meta.get("duration", 6.0)),
            fps=int(meta.get("fps", 24)),
            seed=meta.get("seed"),
            model_id=meta.get("model_id"),
            pollinations_model=meta.get("pollinations_model"),
            source_type=source_type or "video",
        )
        return path.read_bytes(), "video/mp4"

    chain = engine_chain() if ENGINE_MODE == "auto" else [active_engine()]
    logger.info("Generation chain=%s kind=%s", chain, kind)
    last_error: Exception | None = None

    for engine in chain:
        try:
            if engine == "pollinations":
                path, content_type = await _run_pollinations(meta)
            elif engine == "local":
                loop = asyncio.get_event_loop()
                path, content_type = await loop.run_in_executor(
                    EXECUTOR,
                    lambda: _run_local(meta, progress_cb),
                )
            else:
                break
            data = path.read_bytes()
            if len(data) > 1000:
                logger.info("Generated with engine=%s bytes=%s", engine, len(data))
                return data, content_type
        except Exception as exc:
            logger.warning("Engine %s failed: %s", engine, exc)
            last_error = exc
            continue

    # Motion-synthesis fallback (no Pollinations / no local models)
    prompt = meta.get("prompt", "")
    w = int(meta.get("width", 512))
    h = int(meta.get("height", 512))
    kind = meta.get("output_kind", "video")
    duration = float(meta.get("duration", 4.0))
    seed = meta.get("seed")

    if kind == "image":
        path = await generate_prompt_image(prompt, w, h, seed=seed)
        return path.read_bytes(), "image/png"
    if kind == "audio":
        path = await generate_prompt_audio(prompt, duration=min(duration, 6.0))
        return path.read_bytes(), "audio/mpeg"

    path = await generate_prompt_video(
        prompt, w, h,
        duration=duration,
        fps=int(meta.get("fps", 24)),
        seed=seed,
        model_id=meta.get("model_id"),
        pollinations_model=meta.get("pollinations_model"),
        allow_motion_fallback=True,
    )
    return path.read_bytes(), "video/mp4"


async def status(request):
    engine = active_engine()
    labels = {
        "local": "local-animatediff",
        "pollinations": "pollinations-true-video",
        "fallback": "motion-synthesis",
    }
    chain = engine_chain()
    return web.json_response({
        "status": "ok",
        "engine": labels.get(engine, engine),
        "engine_mode": ENGINE_MODE,
        "engine_chain": [labels.get(e, e) for e in chain],
        "pollinations_ready": true_video_enabled(),
        "models_ready": models_ready(),
        "true_video": engine in ("local", "pollinations"),
        "local_models": {
            "sd15": "stable-diffusion-v1-5",
            "motion": "animatediff-motion-adapter-v1-5-2",
        },
    })


async def queue(request):
    return web.json_response({})


async def system(request):
    return web.json_response({
        "models": ["animatediff-local", "stable-diffusion-v1-5"],
        "status": "ready" if models_ready() else "models_missing",
        "engine": active_engine(),
    })


async def prompt(request):
    data = await request.json()
    workflow = data.get("prompt", {})
    client_id = data.get("client_id")
    prompt_id = f"gen-{int(time.time() * 1000)}"

    meta = _extract_from_workflow(workflow)
    meta["prompt_id"] = prompt_id
    PROMPT_META[prompt_id] = meta
    if client_id:
        SESSIONS[client_id] = meta

    return web.json_response({"prompt_id": prompt_id})


async def view(request):
    prompt_id = request.query.get("prompt_id")
    client_id = request.query.get("clientId")
    if prompt_id and prompt_id in OUTPUT_CACHE:
        data, content_type = OUTPUT_CACHE[prompt_id]
        return web.Response(body=data, content_type=content_type)

    meta = PROMPT_META.get(prompt_id) if prompt_id else None
    if not meta and client_id:
        meta = SESSIONS.get(client_id)
    if not meta:
        meta = _extract_from_workflow({})

    try:
        data, content_type = await _resolve_output(meta)
    except Exception as exc:
        logger.exception("Generation failed")
        return web.json_response({"error": str(exc)}, status=500)

    if prompt_id:
        OUTPUT_CACHE[prompt_id] = (data, content_type)
    return web.Response(body=data, content_type=content_type)


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_id = request.query.get("clientId")
    prompt_id = request.query.get("promptId")
    meta = {}
    if prompt_id and prompt_id in PROMPT_META:
        meta = dict(PROMPT_META[prompt_id])
    elif client_id:
        meta = dict(SESSIONS.get(client_id, {}))
    if not prompt_id:
        prompt_id = meta.get("prompt_id", f"gen-{int(time.time())}")
    output_kind = meta.get("output_kind", "video")

    progress_state = {"value": 0.0}

    def progress_cb(value: float) -> None:
        progress_state["value"] = value

    try:
        await ws.send_json({"type": "progress", "data": {"value": 2, "max": 100}})

        async def _generate():
            return await _resolve_output(meta, progress_cb=progress_cb)

        task = asyncio.create_task(_generate())

        while not task.done():
            pct = int(max(2, min(98, progress_state["value"] * 100)))
            await ws.send_json({"type": "progress", "data": {"value": pct, "max": 100}})
            await asyncio.sleep(0.5)

        data, content_type = await task
        OUTPUT_CACHE[prompt_id] = (data, content_type)

        if output_kind == "image":
            output = {"images": [{"filename": "output.png", "subfolder": "", "prompt_id": prompt_id}]}
        elif output_kind == "audio":
            output = {"audio": [{"filename": "output.mp3", "subfolder": "", "prompt_id": prompt_id}]}
        else:
            output = {"videos": [{"filename": "output.mp4", "subfolder": "", "prompt_id": prompt_id}]}

        await ws.send_json({"type": "progress", "data": {"value": 100, "max": 100}})
        await ws.send_json({"type": "executed", "data": {"prompt_id": prompt_id, "output": output}})
    except Exception as exc:
        logger.exception("WS generation failed")
        await ws.send_json({"type": "execution_error", "data": {"prompt_id": prompt_id, "error": str(exc)}})
    finally:
        await ws.close()
    return ws


def create_app():
    app = web.Application()
    app.router.add_get("/status", status)
    app.router.add_get("/queue", queue)
    app.router.add_get("/system", system)
    app.router.add_post("/prompt", prompt)
    app.router.add_get("/view", view)
    app.router.add_get("/ws", ws_handler)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if AUTO_DOWNLOAD and not models_ready() and ENGINE_MODE in ("local", "auto"):
        logger.info("Local models missing — starting download (~6 GB)...")
        from download_models import download_all

        try:
            download_all()
        except Exception:
            logger.exception("Model download failed; fallback engine will be used until models are present")

    engine = active_engine()
    print(f"ComfyUI server running on http://0.0.0.0:8188 (engine={engine}, models_ready={models_ready()})")
    web.run_app(create_app(), host="0.0.0.0", port=8188)
