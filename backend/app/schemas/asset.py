from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.services.youtube_downloader import is_youtube_url


class YouTubeDownloadRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=2048)
    project_id: str | None = None

    @field_validator("url")
    @classmethod
    def validate_youtube_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not is_youtube_url(cleaned):
            raise ValueError("Provide a valid YouTube URL (youtube.com or youtu.be)")
        return cleaned
