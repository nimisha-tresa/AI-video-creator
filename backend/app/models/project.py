from __future__ import annotations

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin, new_uuid


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Timeline data: tracks, clips, settings stored as JSONB
    timeline_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)

    # Video settings
    fps: Mapped[int] = mapped_column(Integer, default=24)
    width: Mapped[int] = mapped_column(Integer, default=1024)
    height: Mapped[int] = mapped_column(Integer, default=576)
    duration_frames: Mapped[int] = mapped_column(Integer, default=0)

    owner: Mapped["User"] = relationship(back_populates="projects")  # noqa: F821
    assets: Mapped[list["Asset"]] = relationship(back_populates="project", lazy="select")  # noqa: F821
    generations: Mapped[list["Generation"]] = relationship(back_populates="project", lazy="select")  # noqa: F821
