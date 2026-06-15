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
        self._http = httpx.AsyncClient(base_url=self.base_url, timeout=settings.comfyui_timeout)
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
        ws_url = self.base_url.replace("http", "ws") + f"/ws?clientId={self.client_id}"
        async with websockets.connect(ws_url) as ws:
            while True:
                raw = await ws.recv()
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

    async def _download_output(self, output: dict) -> bytes:
        """Download the first image or video from the ComfyUI output node."""
        images = output.get("images", [])
        videos = output.get("gifs", output.get("videos", []))
        items = images or videos
        if not items:
            raise RuntimeError("No output produced by ComfyUI workflow")

        item = items[0]
        filename = item["filename"]
        subfolder = item.get("subfolder", "")
        params = f"filename={filename}&subfolder={subfolder}&type=output"
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
        prompt_id = await self._queue_prompt(workflow)
        logger.info("Workflow queued", prompt_id=prompt_id)

        output = await self._wait_for_completion(prompt_id, on_progress)

        # Detect output type
        is_video = bool(output.get("gifs") or output.get("videos"))
        content_type = "video/mp4" if is_video else "image/png"
        ext = ".mp4" if is_video else ".png"

        data = await self._download_output(output)
        key = upload_bytes(data, f"output{ext}", content_type, bucket=settings.minio_bucket_output)

        from app.services.storage import get_presigned_url

        url = get_presigned_url(key, bucket=settings.minio_bucket_output)

        # Extract seed if present (from KSampler node)
        seed = None
        for node_output in output.values():
            if isinstance(node_output, dict) and "seed" in node_output:
                seed = node_output["seed"]
                break

        if on_progress:
            on_progress(1.0)

        return {"url": url, "key": key, "seed": seed}
