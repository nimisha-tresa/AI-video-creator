from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.generation import GenerationStatus, GenerationType


class GenerationParams(BaseModel):
    # Video processing
    num_frames: int = Field(default=16, ge=8, le=192)
    fps: int = Field(default=12, ge=4, le=30)
    width: int = Field(default=720, ge=256, le=1280)
    height: int = Field(default=1280, ge=256, le=1920)  # Portrait for Shorts
    
    # Prompt/style parameters
    strength: float = Field(default=0.8, ge=0.0, le=1.0)  # How strong to apply effect
    
    extra: dict[str, Any] = {}


class GenerationCreate(BaseModel):
    type: GenerationType | None = None
    model_id: str | None = None
    prompt: str | None = None
    negative_prompt: str | None = None
    params: GenerationParams = GenerationParams()
    project_id: str | None = None
    source_asset_id: str | None = None  # img2img / img2video source
    clear_previous: bool = True  # remove older generations + output files before creating


class GenerationRead(BaseModel):
    id: str
    owner_id: str
    project_id: str | None
    type: GenerationType
    status: GenerationStatus
    prompt: str | None
    negative_prompt: str | None
    params: dict
    output_url: str | None
    thumbnail_url: str | None
    error_message: str | None
    task_id: str | None
    progress: float
    gpu_seconds: float
    width: int
    height: int
    num_frames: int
    seed: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GenerationUpdate(BaseModel):
    status: GenerationStatus | None = None
    progress: float | None = None
    output_url: str | None = None
    error_message: str | None = None
