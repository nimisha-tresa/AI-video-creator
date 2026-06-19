from __future__ import annotations

import enum

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class GenerationType(str, enum.Enum):
    TEXT_TO_IMAGE = "text_to_image"
    IMAGE_TO_IMAGE = "image_to_image"
    TEXT_TO_VIDEO = "text_to_video"
    IMAGE_TO_VIDEO = "image_to_video"
    VIDEO_ENHANCE = "video_enhance"
    TEXT_TO_AUDIO = "text_to_audio"


class GenerationStatus(str, enum.Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Generation(Base, TimestampMixin):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True, nullable=True
    )

    type: Mapped[GenerationType] = mapped_column(
        Enum(GenerationType, values_callable=lambda x: [e.value for e in x], native_enum=False),
        nullable=False,
    )
    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, values_callable=lambda x: [e.value for e in x], native_enum=False),
        default=GenerationStatus.PENDING,
        index=True,
    )

    # Prompt
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Generation parameters
    params: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Results
    output_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Celery task
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Progress (0.0 – 1.0)
    progress: Mapped[float] = mapped_column(Float, default=0.0)

    # Cost tracking
    gpu_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    # Metadata
    width: Mapped[int] = mapped_column(Integer, default=1024)
    height: Mapped[int] = mapped_column(Integer, default=576)
    num_frames: Mapped[int] = mapped_column(Integer, default=16)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)

    owner: Mapped["User"] = relationship(back_populates="generations")  # noqa: F821
    project: Mapped["Project | None"] = relationship(back_populates="generations")  # noqa: F821
