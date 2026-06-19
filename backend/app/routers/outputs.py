from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from minio.error import S3Error

from app.services.storage import get_minio_client
from app.config import get_settings

settings = get_settings()

router = APIRouter(prefix="/outputs", tags=["outputs"])


@router.get("/{key}")
def get_output(key: str):
    """Proxy an object from the MinIO `output` bucket so the host can
    retrieve it without needing presigned URL routing or signature rewrites.
    """
    client = get_minio_client()
    try:
        # Get metadata to determine content-type
        stat = client.stat_object(settings.minio_bucket_output, key)
        content_type = getattr(stat, "content_type", "application/octet-stream")
        obj = client.get_object(settings.minio_bucket_output, key)
    except S3Error:
        raise HTTPException(status_code=404, detail="Output not found")

    return StreamingResponse(obj, media_type=content_type)


@router.get("/local_outputs/{filename}")
def get_local_output(filename: str):
    """Serve a file written to `settings.local_output_dir`.

    Files are saved in the backend workspace (useful for development)."""
    import os
    from pathlib import Path

    local_dir = Path(settings.local_output_dir)
    file_path = local_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Local output not found")

    # Map common extensions to media types (fallback to octet-stream)
    ext = file_path.suffix.lower()
    media_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
    }
    media_type = media_map.get(ext, "application/octet-stream")
    return FileResponse(
        file_path,
        media_type=media_type,
        filename=filename,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"},
    )
