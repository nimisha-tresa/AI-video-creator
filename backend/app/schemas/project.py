from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class TimelineClip(BaseModel):
    id: str
    track_id: str
    type: str  # "generation" | "asset" | "transition"
    source_id: str | None = None
    start_frame: int
    end_frame: int
    in_point: int = 0
    properties: dict[str, Any] = {}


class TimelineTrack(BaseModel):
    id: str
    name: str
    type: str  # "video" | "audio" | "overlay"
    clips: list[TimelineClip] = []
    locked: bool = False
    visible: bool = True


class TimelineData(BaseModel):
    tracks: list[TimelineTrack] = []
    markers: list[dict] = []


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    fps: int = 24
    width: int = 1024
    height: int = 576


class ProjectRead(BaseModel):
    id: str
    owner_id: str
    title: str
    description: str | None
    thumbnail_url: str | None
    timeline_data: dict
    fps: int
    width: int
    height: int
    duration_frames: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    timeline_data: dict | None = None
    duration_frames: int | None = None
