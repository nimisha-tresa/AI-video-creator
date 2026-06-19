from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Callable

import httpx
import structlog
import websockets

from app.config import get_settings
from app.services.storage import upload_bytes

settings = get_settings()
logger = structlog.get_logger()


class ComfyUIClient:
    """
    Async client for ComfyUI's HTTP + WebSocket API.
    Submits a workflow, streams progress via WebSocket, downloads
    the output image/video, and uploads it to MinIO.
    """

    def __init__(self, base_url: str | None = None) -> None:
        self.base_url = (base_url or settings.comfyui_url).rstrip("/")
        self.client_id = str(uuid.uuid4())
        self._http: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "ComfyUIClient":
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=settings.comfyui_timeout,
            trust_env=False,
        )
        return self

    async def __aexit__(self, *_) -> None:
        if self._http:
            await self._http.aclose()

    async def _queue_prompt(self, workflow: dict) -> str:
        payload = {"prompt": workflow, "client_id": self.client_id}
        resp = await self._http.post("/prompt", json=payload)
        resp.raise_for_status()
        return resp.json()["prompt_id"]

    async def _wait_for_completion(
        self, prompt_id: str, on_progress: Callable[[float], None] | None = None
    ) -> dict[str, Any]:
        ws_url = self.base_url.replace("http", "ws") + f"/ws?clientId={self.client_id}&promptId={prompt_id}"
        deadline = asyncio.get_running_loop().time() + settings.comfyui_timeout

        try:
            async with websockets.connect(ws_url, open_timeout=15, close_timeout=5) as ws:
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"ComfyUI did not produce output within {settings.comfyui_timeout}s"
                        )
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
                    except asyncio.TimeoutError as exc:
                        raise TimeoutError(
                            f"ComfyUI did not produce output within {settings.comfyui_timeout}s"
                        ) from exc

                    if isinstance(raw, bytes):
                        continue
                    msg = json.loads(raw)
                    msg_type = msg.get("type")

                    if msg_type == "progress" and on_progress:
                        data = msg.get("data", {})
                        value = data.get("value", 0)
                        maximum = data.get("max", 1)
                        frac = min(value / max(maximum, 1), 0.98)
                        on_progress(0.05 + frac * 0.90)  # map 5% → 95%

                    elif msg_type == "executed":
                        data = msg.get("data", {})
                        if data.get("prompt_id") == prompt_id:
                            return data.get("output", {})

                    elif msg_type == "execution_error":
                        data = msg.get("data", {})
                        raise RuntimeError(f"ComfyUI execution error: {data}")
        except websockets.exceptions.InvalidMessage as exc:
            raise RuntimeError(
                f"ComfyUI WebSocket unavailable at {self.base_url}. "
                "The inference engine may be down or misconfigured."
            ) from exc

    async def _download_output(self, output: dict, prompt_id: str | None = None) -> bytes:
        """Download the first image, video, or audio from the ComfyUI output node."""
        images = output.get("images", [])
        videos = output.get("gifs", output.get("videos", []))
        audio = output.get("audio", [])
        items = images or videos or audio
        if not items:
            raise RuntimeError("No output produced by ComfyUI workflow")

        item = items[0]
        filename = item.get("filename", "output")
        subfolder = item.get("subfolder", "")
        item_prompt_id = item.get("prompt_id") or prompt_id
        params = f"filename={filename}&subfolder={subfolder}&type=output"
        if item_prompt_id:
            params += f"&prompt_id={item_prompt_id}"
        params += f"&clientId={self.client_id}"
        resp = await self._http.get(f"/view?{params}")
        resp.raise_for_status()
        return resp.content

    async def run_workflow(
        self,
        workflow: dict,
        on_progress: Callable[[float], None] | None = None,
    ) -> dict[str, Any]:
        """
        Submit workflow → wait for completion → download output → upload to MinIO.
        Returns {"url": presigned_url, "seed": optional_seed}.
        """
        logger.info("Connecting to ComfyUI", url=self.base_url, timeout=settings.comfyui_timeout)
        try:
            prompt_id = await self._queue_prompt(workflow)
            logger.info("Workflow queued successfully", prompt_id=prompt_id, url=self.base_url)
        except Exception as e:
            logger.error("Failed to connect/queue to ComfyUI", url=self.base_url, error_type=type(e).__name__, error=str(e))
            raise RuntimeError(f"ComfyUI connection failed at {self.base_url}: {e}") from e

        try:
            output = await self._wait_for_completion(prompt_id, on_progress)
        except Exception as e:
            logger.error("Workflow execution failed or timed out", prompt_id=prompt_id, url=self.base_url, error_type=type(e).__name__, error=str(e))
            raise

        logger.info("Workflow completed, processing output", output_keys=list(output.keys()) if isinstance(output, dict) else type(output))

        # Detect output type
        is_video = bool(output.get("gifs") or output.get("videos"))
        is_audio = bool(output.get("audio"))
        if is_video:
            content_type, ext = "video/mp4", ".mp4"
        elif is_audio:
            content_type, ext = "audio/mpeg", ".mp3"
        else:
            content_type, ext = "image/png", ".png"
        logger.info("Output type detected", is_video=is_video, is_audio=is_audio, content_type=content_type)

        try:
            data = await self._download_output(output, prompt_id=prompt_id)
            logger.info("Output downloaded successfully", size_mb=len(data) / 1024 / 1024)
        except Exception as e:
            logger.error("Failed to download output from ComfyUI", error_type=type(e).__name__, error=str(e))
            raise

        # Save output locally inside the backend workspace (mounted into the
        # container at /app). This makes outputs directly accessible on the
        # host filesystem during development.
        import os
        from pathlib import Path

        local_dir = Path(settings.local_output_dir)
        # Ensure directory exists (relative to app root)
        local_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}{ext}"
        filepath = local_dir / filename
        with open(filepath, "wb") as f:
            f.write(data)

        # Expose via API proxy: http://localhost:8000/local_outputs/{filename}
        url = f"{settings.api_base_url.rstrip('/')}/local_outputs/{filename}"
        key = str(filename)

        # Extract seed if present (from KSampler node)
        seed = None
        for node_output in output.values():
            if isinstance(node_output, dict) and "seed" in node_output:
                seed = node_output["seed"]
                break

        if on_progress:
            on_progress(1.0)

        return {"url": url, "key": key, "seed": seed}
