from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.generation import GenerationStatus, GenerationType


class GenerationParams(BaseModel):
    # SDXL / Image
    steps: int = Field(default=30, ge=1, le=150)
    cfg_scale: float = Field(default=7.0, ge=1.0, le=30.0)
    sampler: str = "dpmpp_2m"
    scheduler: str = "karras"
    seed: int | None = None

    # AnimateDiff / Video
    num_frames: int = Field(default=16, ge=8, le=128)
    fps: int = Field(default=8, ge=4, le=30)
    motion_module: str = "mm_sd_v15_v2.ckpt"
    motion_scale: float = Field(default=1.0, ge=0.5, le=2.0)

    # IP-Adapter
    ip_adapter_enabled: bool = False
    ip_adapter_scale: float = Field(default=0.6, ge=0.0, le=1.0)
    ip_adapter_image_id: str | None = None  # Asset ID for reference image

    # Dimensions
    width: int = Field(default=1024, ge=256, le=2048)
    height: int = Field(default=576, ge=256, le=2048)

    # ControlNet (optional)
    controlnet_enabled: bool = False
    controlnet_type: str = "openpose"
    controlnet_scale: float = Field(default=0.8, ge=0.0, le=2.0)
    controlnet_image_id: str | None = None

    extra: dict[str, Any] = {}


class GenerationCreate(BaseModel):
    type: GenerationType
    prompt: str | None = None
    negative_prompt: str | None = None
    params: GenerationParams = GenerationParams()
    project_id: str | None = None
    source_asset_id: str | None = None  # img2img / img2video source


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
