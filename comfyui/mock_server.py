#!/usr/bin/env python3
"""ComfyUI-compatible server — prompt-analyzed AI video/image generation."""

from __future__ import annotations

import asyncio
import time

from aiohttp import web

from prompt_engine import analyze_prompt, generate_prompt_audio, generate_prompt_image, generate_prompt_video, true_video_enabled

SESSIONS: dict[str, dict] = {}
PROMPT_META: dict[str, dict] = {}


def _extract_from_workflow(workflow: dict) -> dict:
    prompt = ""
    model_id = "veo-3.1"
    theme = "default"
    pollinations_model = "veo"
    width, height = 1280, 720
    output_kind = "video"
    duration = 4.0
    fps = 24

    for node in workflow.values():
        if not isinstance(node, dict):
            continue
        ctype = node.get("class_type", "")
        inputs = node.get("inputs", {})

        if ctype == "CLIPTextEncode" and not prompt:
            text = inputs.get("text", "")
            if text and "bad quality" not in text.lower() and "blurry" not in text.lower():
                prompt = text
        elif ctype == "MockModelInfo":
            model_id = inputs.get("model_id", model_id)
            theme = inputs.get("visual_theme", theme)
            output_kind = inputs.get("output_kind", output_kind)
            pollinations_model = inputs.get("pollinations_model", pollinations_model)
        elif ctype == "EmptyLatentImage":
            width = int(inputs.get("width", width))
            height = int(inputs.get("height", height))
            batch = int(inputs.get("batch_size", 16))
            duration = max(2.0, min(batch / 8, 12.0))
        elif ctype == "SaveImage":
            output_kind = "image"

    analysis = analyze_prompt(prompt)
    return {
        "prompt": prompt,
        "model_id": model_id,
        "pollinations_model": pollinations_model,
        "theme": theme,
        "width": width,
        "height": height,
        "output_kind": output_kind,
        "duration": duration,
        "fps": fps,
        "analysis": analysis,
    }


async def _resolve_output(meta: dict) -> tuple[bytes, str]:
    prompt = meta.get("prompt", "")
    w = int(meta.get("width", 1280))
    h = int(meta.get("height", 720))
    kind = meta.get("output_kind", "video")
    duration = float(meta.get("duration", 4.0))
    seed = hash(prompt) % 999_999

    if kind == "image":
        path = await generate_prompt_image(prompt, w, h, seed=seed)
        return path.read_bytes(), "image/png"
    if kind == "audio":
        path = await generate_prompt_audio(prompt, duration=min(duration, 6.0))
        return path.read_bytes(), "audio/mpeg"

    path = await generate_prompt_video(
        prompt, w, h,
        duration=duration, fps=24, seed=seed,
        model_id=meta.get("model_id"),
        pollinations_model=meta.get("pollinations_model"),
    )
    return path.read_bytes(), "video/mp4"


async def status(request):
    return web.json_response({
        "status": "ok",
        "engine": "pollinations-true-video" if true_video_enabled() else "motion-synthesis",
        "true_video": true_video_enabled(),
    })


async def queue(request):
    return web.json_response({})


async def system(request):
    return web.json_response({"models": ["flux", "animatediff"], "status": "ready", "prompt_engine": True})


async def prompt(request):
    data = await request.json()
    workflow = data.get("prompt", {})
    client_id = data.get("client_id")
    prompt_id = f"mock-{int(time.time() * 1000)}"

    meta = _extract_from_workflow(workflow)
    meta["prompt_id"] = prompt_id
    PROMPT_META[prompt_id] = meta
    if client_id:
        SESSIONS[client_id] = meta

    return web.json_response({"prompt_id": prompt_id})


async def view(request):
    prompt_id = request.query.get("prompt_id")
    client_id = request.query.get("clientId")
    meta = PROMPT_META.get(prompt_id) if prompt_id else None
    if not meta and client_id:
        meta = SESSIONS.get(client_id)

    if not meta:
        meta = _extract_from_workflow({})

    try:
        data, content_type = await _resolve_output(meta)
    except Exception as exc:
        return web.json_response({"error": str(exc)}, status=500)

    return web.Response(body=data, content_type=content_type)


async def ws_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_id = request.query.get("clientId")
    meta = SESSIONS.get(client_id, {})
    prompt_id = meta.get("prompt_id", f"mock-{int(time.time())}")
    output_kind = meta.get("output_kind", "video")

    try:
        # Progress while fetching 6 AI frames + assembling motion clips
        for v in range(0, 101, 4):
            await ws.send_json({"type": "progress", "data": {"value": v, "max": 100}})
            await asyncio.sleep(0.45 if v < 60 else 0.8)

        if output_kind == "image":
            output = {"images": [{"filename": "output.png", "subfolder": "", "prompt_id": prompt_id}]}
        elif output_kind == "audio":
            output = {"audio": [{"filename": "output.mp3", "subfolder": "", "prompt_id": prompt_id}]}
        else:
            output = {"videos": [{"filename": "output.mp4", "subfolder": "", "prompt_id": prompt_id}]}

        await ws.send_json({"type": "executed", "data": {"prompt_id": prompt_id, "output": output}})
    except asyncio.CancelledError:
        pass
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
    app = create_app()
    print("ComfyUI Prompt Engine running on http://0.0.0.0:8188")
    web.run_app(app, host="0.0.0.0", port=8188)
