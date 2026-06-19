from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.asset import Asset, AssetType
from app.models.generation import Generation, GenerationStatus, GenerationType
from app.models.user import User
from app.schemas.generation import GenerationCreate, GenerationRead
from app.services.generation_stale import mark_stale_generations_failed

settings = get_settings()

router = APIRouter(prefix="/generations", tags=["generations"])


@router.get("/", response_model=list[GenerationRead])
async def list_generations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    q = select(Generation).options(selectinload(Generation.owner), selectinload(Generation.project)).where(Generation.owner_id == user.id)
    if project_id:
        q = q.where(Generation.project_id == project_id)
    q = q.order_by(Generation.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    generations = result.scalars().all()
    await mark_stale_generations_failed(db, generations)
    return generations


@router.post("/", response_model=GenerationRead, status_code=status.HTTP_201_CREATED)
async def create_generation(
    data: GenerationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from workers.tasks.dispatch import dispatch_generation
    from app.services.model_registry import get_model
    import structlog
    
    logger = structlog.get_logger()

    model = get_model(data.model_id) if data.model_id else None
    source_asset: Asset | None = None
    if data.source_asset_id:
        asset_result = await db.execute(
            select(Asset).where(Asset.id == data.source_asset_id, Asset.owner_id == user.id)
        )
        source_asset = asset_result.scalar_one_or_none()
        if not source_asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source asset not found")
        if source_asset.type == AssetType.VIDEO:
            gen_type = GenerationType.VIDEO_ENHANCE
        elif source_asset.type == AssetType.IMAGE:
            gen_type = GenerationType.IMAGE_TO_VIDEO
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Source asset must be an image or video",
            )
    elif model:
        gen_type = GenerationType(model.generation_type)
    elif data.type:
        gen_type = data.type
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide model_id or type")

    if data.clear_previous:
        from app.services.generation_cleanup import clear_user_generations

        cleared = await clear_user_generations(db, user.id)
        logger.info("Previous generations cleared before new create", user_id=user.id, cleared=cleared)

    params_dict = data.params.model_dump()
    extra = dict(params_dict.get("extra") or {})
    if data.model_id:
        extra["model_id"] = data.model_id
    if model:
        params_dict["fps"] = model.preset.fps
        params_dict["steps"] = model.preset.steps
        extra["visual_theme"] = model.preset.visual_theme
        if model.pollinations_model:
            extra["pollinations_model"] = model.pollinations_model
        if model.category == "video":
            params_dict["num_frames"] = min(192, max(8, model.preset.duration_sec * model.preset.fps))
        elif model.category in ("image", "llm", "audio"):
            params_dict["num_frames"] = 1
    if source_asset:
        internal_base = settings.internal_api_url.rstrip("/")
        extra["source_asset_id"] = source_asset.id
        extra["source_asset_url"] = f"{internal_base}/assets/internal_assets/{source_asset.storage_key}"
        extra["source_asset_type"] = source_asset.type.value
        if source_asset.duration_ms:
            params_dict["source_duration_sec"] = max(1, round(source_asset.duration_ms / 1000))
        if source_asset.width:
            params_dict["width"] = source_asset.width
        if source_asset.height:
            params_dict["height"] = source_asset.height
    params_dict["extra"] = extra

    generation = Generation(
        owner_id=user.id,
        project_id=data.project_id,
        type=gen_type,
        prompt=data.prompt,
        negative_prompt=data.negative_prompt,
        params=params_dict,
        status=GenerationStatus.PENDING,
        width=data.params.width,
        height=data.params.height,
        num_frames=params_dict["num_frames"],
    )
    db.add(generation)
    await db.commit()
    await db.refresh(generation)

    # Dispatch to Celery with error handling
    try:
        task = dispatch_generation.delay(generation.id)
        generation.task_id = task.id
        generation.status = GenerationStatus.QUEUED
    except Exception as exc:
        logger.exception("Failed to dispatch generation task", generation_id=generation.id, error=str(exc))
        generation.status = GenerationStatus.PENDING
        generation.error_message = f"Task dispatch failed: {str(exc)}"
    
    await db.commit()
    # Re-query with eager loads to ensure no IO is attempted during
    # Pydantic serialization (avoids MissingGreenlet errors).
    result = await db.execute(
        select(Generation).options(selectinload(Generation.owner), selectinload(Generation.project)).where(
            Generation.id == generation.id
        )
    )
    gen = result.scalar_one()
    return gen


@router.get("/{generation_id}", response_model=GenerationRead)
async def get_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Generation).options(selectinload(Generation.owner), selectinload(Generation.project)).where(
            Generation.id == generation_id, Generation.owner_id == user.id
        )
    )
    gen = result.scalar_one_or_none()
    if not gen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    await mark_stale_generations_failed(db, [gen])
    return gen


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
async def clear_generations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete all generations and local output files for the current user."""
    from app.services.generation_cleanup import clear_user_generations

    await clear_user_generations(db, user.id)
    await db.commit()


@router.delete("/{generation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from workers.celery_app import celery_app

    result = await db.execute(
        select(Generation).options(selectinload(Generation.owner), selectinload(Generation.project)).where(
            Generation.id == generation_id, Generation.owner_id == user.id
        )
    )
    gen = result.scalar_one_or_none()
    if not gen:
        raise HTTPException(status_code=404, detail="Generation not found")
    if gen.task_id:
        celery_app.control.revoke(gen.task_id, terminate=True)
    gen.status = GenerationStatus.CANCELLED
    await db.commit()
