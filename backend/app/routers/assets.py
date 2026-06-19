from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from minio.error import S3Error
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.asset import Asset, AssetType
from app.models.user import User
from app.schemas.asset import YouTubeDownloadRequest
from app.services import storage
from app.services.youtube_downloader import download_youtube_video

settings = get_settings()

router = APIRouter(prefix="/assets", tags=["assets"])

MIME_TO_TYPE = {
    "image/jpeg": AssetType.IMAGE,
    "image/png": AssetType.IMAGE,
    "image/webp": AssetType.IMAGE,
    "video/mp4": AssetType.VIDEO,
    "video/webm": AssetType.VIDEO,
    "audio/mpeg": AssetType.AUDIO,
    "audio/wav": AssetType.AUDIO,
}


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: UploadFile = File(...),
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if file.content_type not in MIME_TO_TYPE:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    data = await file.read()
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(status_code=413, detail="File too large")

    key = storage.upload_bytes(data, file.filename or "upload", file.content_type)
    url = storage.get_presigned_url(key)

    asset = Asset(
        owner_id=user.id,
        project_id=project_id,
        type=MIME_TO_TYPE[file.content_type],
        filename=file.filename or "upload",
        storage_key=key,
        url=url,
        mime_type=file.content_type,
        size_bytes=len(data),
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.post("/youtube", status_code=status.HTTP_201_CREATED)
async def download_youtube_asset(
    body: YouTubeDownloadRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data, filename = download_youtube_video(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    key = storage.upload_bytes(data, filename, "video/mp4")
    url = storage.get_presigned_url(key)

    asset = Asset(
        owner_id=user.id,
        project_id=body.project_id,
        type=AssetType.VIDEO,
        filename=filename,
        storage_key=key,
        url=url,
        mime_type="video/mp4",
        size_bytes=len(data),
    )
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


@router.get("/")
async def list_assets(
    project_id: str | None = None,
    asset_type: AssetType | None = None,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(Asset).where(Asset.owner_id == user.id)
    if project_id:
        q = q.where(Asset.project_id == project_id)
    if asset_type:
        q = q.where(Asset.type == asset_type)
    q = q.order_by(Asset.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_asset(
    asset_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Asset).where(Asset.id == asset_id, Asset.owner_id == user.id)
    )
    asset = result.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    try:
        storage.delete_object(asset.storage_key)
    except Exception:
        pass
    await db.delete(asset)
    await db.commit()


@router.get("/internal_assets/{key}")
async def internal_asset(key: str):
    """Internal proxy to stream an asset from MinIO for other services within
    the Docker network (e.g. ComfyUI). This is intentionally unprotected and
    should only be used by internal services.
    """
    client = storage.get_minio_client()
    try:
        obj = client.get_object(settings.minio_bucket_assets, key)
    except S3Error:
        raise HTTPException(status_code=404, detail="Asset not found")

    return StreamingResponse(obj, media_type="application/octet-stream")
