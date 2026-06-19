from __future__ import annotations

import re
import tempfile
from pathlib import Path

import yt_dlp

from app.config import get_settings

settings = get_settings()

_YOUTUBE_HOSTS = (
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
)


def is_youtube_url(url: str) -> bool:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        return False
    return any(host in cleaned.lower() for host in _YOUTUBE_HOSTS)


def _safe_filename(title: str, video_id: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
    slug = slug[:80] or video_id
    return f"{slug}.mp4"


def download_youtube_video(url: str) -> tuple[bytes, str]:
    """Download a YouTube video as MP4 (max 720p). Returns (data, filename)."""
    if not is_youtube_url(url):
        raise ValueError("URL must be a YouTube link (youtube.com or youtu.be)")

    max_bytes = settings.max_upload_size_bytes

    with tempfile.TemporaryDirectory(prefix="yt_") as tmp:
        out_dir = Path(tmp)
        outtmpl = str(out_dir / "%(id)s.%(ext)s")
        ydl_opts: dict = {
            "format": "best[ext=mp4][height<=720]/best[height<=720]/best",
            "merge_output_format": "mp4",
            "outtmpl": outtmpl,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            raise ValueError(f"YouTube download failed: {exc}") from exc

        if not info:
            raise ValueError("Could not fetch video information from YouTube")

        video_id = info.get("id") or "video"
        title = info.get("title") or video_id
        candidates = list(out_dir.glob(f"{video_id}.*"))
        if not candidates:
            candidates = sorted(out_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)

        if not candidates:
            raise ValueError("YouTube download completed but no file was produced")

        filepath = candidates[0]
        data = filepath.read_bytes()
        if len(data) < 10_000:
            raise ValueError("Downloaded video is too small or invalid")
        if len(data) > max_bytes:
            raise ValueError(
                f"Video exceeds upload limit ({settings.max_upload_size_mb} MB). "
                "Try a shorter clip or increase MAX_UPLOAD_SIZE_MB."
            )

        return data, _safe_filename(title, video_id)
