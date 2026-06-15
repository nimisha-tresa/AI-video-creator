from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.generation import Generation, GenerationStatus
from app.models.user import User
from app.schemas.generation import GenerationCreate, GenerationRead

router = APIRouter(prefix="/generations", tags=["generations"])


@router.get("/", response_model=list[GenerationRead])
async def list_generations(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    project_id: str | None = None,
    skip: int = 0,
    limit: int = 50,
):
    q = select(Generation).where(Generation.owner_id == user.id)
    if project_id:
        q = q.where(Generation.project_id == project_id)
    q = q.order_by(Generation.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(q)
    return result.scalars().all()


@router.post("/", response_model=GenerationRead, status_code=status.HTTP_201_CREATED)
async def create_generation(
    data: GenerationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from workers.tasks.dispatch import dispatch_generation

    generation = Generation(
        owner_id=user.id,
        project_id=data.project_id,
        type=data.type,
        prompt=data.prompt,
        negative_prompt=data.negative_prompt,
        params=data.params.model_dump(),
        status=GenerationStatus.PENDING,
        width=data.params.width,
        height=data.params.height,
        num_frames=data.params.num_frames,
    )
    db.add(generation)
    await db.commit()
    await db.refresh(generation)

    # Dispatch to Celery
    task = dispatch_generation.delay(generation.id)
    generation.task_id = task.id
    generation.status = GenerationStatus.QUEUED
    await db.commit()

    return generation


@router.get("/{generation_id}", response_model=GenerationRead)
async def get_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Generation).where(
            Generation.id == generation_id, Generation.owner_id == user.id
        )
    )
    gen = result.scalar_one_or_none()
    if not gen:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Generation not found")
    return gen


@router.delete("/{generation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_generation(
    generation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from workers.celery_app import celery_app

    result = await db.execute(
        select(Generation).where(
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
