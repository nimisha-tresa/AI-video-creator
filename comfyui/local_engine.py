"""Local model inference — AnimateDiff text-to-video + SD 1.5 text-to-image."""

from __future__ import annotations

import logging
import random
import threading
from pathlib import Path
from typing import Callable

from download_models import MOTION_DIR, SD15_DIR, models_ready

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("/app/output")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_lock = threading.Lock()
_video_pipe = None
_image_pipe = None


def _device_and_dtype():
    import torch

    if torch.cuda.is_available():
        return torch.device("cuda"), torch.float16
    return torch.device("cpu"), torch.float32


def _snap_dim(value: int, minimum: int = 256, maximum: int = 512) -> int:
    value = max(minimum, min(value, maximum))
    return value - (value % 8)


def get_video_pipeline():
    global _video_pipe
    if _video_pipe is not None:
        return _video_pipe

    from diffusers import AnimateDiffPipeline, DDIMScheduler, MotionAdapter
    import torch

    device, dtype = _device_and_dtype()
    logger.info("Loading AnimateDiff pipeline on %s (%s)", device, dtype)

    adapter = MotionAdapter.from_pretrained(str(MOTION_DIR), torch_dtype=dtype)
    pipe = AnimateDiffPipeline.from_pretrained(
        str(SD15_DIR),
        motion_adapter=adapter,
        torch_dtype=dtype,
    )
    pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config, beta_schedule="linear")
    pipe.enable_vae_slicing()
    if device.type == "cuda":
        pipe.enable_model_cpu_offload()
    else:
        pipe.to(device)

    _video_pipe = pipe
    return pipe


def get_image_pipeline():
    global _image_pipe
    if _image_pipe is not None:
        return _image_pipe

    from diffusers import StableDiffusionPipeline
    import torch

    device, dtype = _device_and_dtype()
    logger.info("Loading SD 1.5 image pipeline on %s (%s)", device, dtype)

    pipe = StableDiffusionPipeline.from_pretrained(str(SD15_DIR), torch_dtype=dtype)
    if device.type == "cuda":
        pipe.enable_model_cpu_offload()
    else:
        pipe.to(device)

    _image_pipe = pipe
    return pipe


def generate_video(
    prompt: str,
    *,
    negative_prompt: str = "bad quality, blurry, distorted, watermark, text",
    width: int = 512,
    height: int = 512,
    num_frames: int = 16,
    fps: int = 8,
    steps: int = 20,
    cfg: float = 7.0,
    seed: int | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    if not models_ready():
        raise RuntimeError("Local models not downloaded. Run: python download_models.py")

    from diffusers.utils import export_to_video

    width = _snap_dim(width)
    height = _snap_dim(height)
    num_frames = max(8, min(int(num_frames), 24))
    seed = seed if seed is not None else random.randint(0, 2**32 - 1)

    def _step_callback(pipe, step_index, timestep, callback_kwargs):
        if on_progress:
            on_progress(min(0.95, (step_index + 1) / max(steps, 1)))
        return callback_kwargs

    with _lock:
        pipe = get_video_pipeline()
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            num_frames=num_frames,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=cfg,
            generator=None if seed is None else __import__("torch").Generator(device="cpu").manual_seed(seed),
            callback_on_step_end=_step_callback,
        )

    frames = result.frames[0]
    out = OUTPUT_DIR / f"local_vid_{seed}.mp4"
    export_to_video(frames, str(out), fps=max(4, min(fps, 16)))
    if on_progress:
        on_progress(1.0)
    logger.info("Local video saved %s (%d frames, %dx%d)", out, num_frames, width, height)
    return out


def generate_image(
    prompt: str,
    *,
    negative_prompt: str = "bad quality, blurry, distorted, watermark",
    width: int = 512,
    height: int = 512,
    steps: int = 25,
    cfg: float = 7.0,
    seed: int | None = None,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    if not models_ready():
        raise RuntimeError("Local models not downloaded. Run: python download_models.py")

    width = _snap_dim(width, maximum=768)
    height = _snap_dim(height, maximum=768)
    seed = seed if seed is not None else random.randint(0, 2**32 - 1)

    def _step_callback(pipe, step_index, timestep, callback_kwargs):
        if on_progress:
            on_progress(min(0.95, (step_index + 1) / max(steps, 1)))
        return callback_kwargs

    with _lock:
        pipe = get_image_pipeline()
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt or None,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=cfg,
            generator=None if seed is None else __import__("torch").Generator(device="cpu").manual_seed(seed),
            callback_on_step_end=_step_callback,
        )

    out = OUTPUT_DIR / f"local_img_{seed}.png"
    result.images[0].save(out)
    if on_progress:
        on_progress(1.0)
    logger.info("Local image saved %s (%dx%d)", out, width, height)
    return out
