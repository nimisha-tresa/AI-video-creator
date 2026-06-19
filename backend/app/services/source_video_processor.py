"""Process uploaded source videos directly with ffmpeg (no AI prompt-to-video)."""

from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

import httpx

from app.config import get_settings

settings = get_settings()


def _probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    data = json.loads(result.stdout)
    return max(0.5, float(data.get("format", {}).get("duration") or 0.5))


def process_uploaded_video(
    source_url: str,
    *,
    width: int = 1280,
    height: int = 720,
    fps: int = 24,
    duration_sec: float | None = None,
) -> str:
    """
    Download the user's uploaded video and re-encode it (scale + keep audio).
    Returns a public local_outputs URL.
    """
    work = Path(settings.local_output_dir)
    work.mkdir(parents=True, exist_ok=True)

    src_path = work / f"_src_{uuid.uuid4().hex}.mp4"
    out_name = f"{uuid.uuid4().hex}.mp4"
    out_path = work / out_name

    response = httpx.get(source_url, timeout=120.0)
    response.raise_for_status()
    if len(response.content) < 10_000:
        raise ValueError("Downloaded source video is too small or invalid")
    src_path.write_bytes(response.content)

    src_duration = _probe_duration(src_path)
    clip_duration = min(duration_sec or src_duration, src_duration, 60.0)
    clip_duration = max(1.0, clip_duration)

    w = max(640, min(int(width), 1920))
    h = max(360, min(int(height), 1920))
    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black"
    )

    cmd = [
        "ffmpeg", "-y", "-i", str(src_path),
        "-t", f"{clip_duration:.3f}",
        "-vf", vf,
        "-r", str(max(12, min(int(fps), 30))),
        "-map", "0:v:0", "-map", "0:a:0?",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-preset", "medium", "-crf", "20", "-g", "30",
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000",
        "-movflags", "+faststart",
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    src_path.unlink(missing_ok=True)
    if result.returncode != 0:
        out_path.unlink(missing_ok=True)
        raise RuntimeError(result.stderr[-800:] if result.stderr else "ffmpeg failed")
    if out_path.stat().st_size < 5000:
        out_path.unlink(missing_ok=True)
        raise RuntimeError("Processed video output is empty")

    return f"{settings.api_base_url.rstrip('/')}/local_outputs/{out_name}"
