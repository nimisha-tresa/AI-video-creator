from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────────
    app_name: str = "VideoCreator"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = False

    # ── Security ─────────────────────────────────────────────────────────────
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 30

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str

    # ── Redis / Celery ───────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # ── MinIO / S3 ───────────────────────────────────────────────────────────
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket_assets: str = "assets"
    minio_bucket_output: str = "output"
    minio_secure: bool = False

    # ── ComfyUI ──────────────────────────────────────────────────────────────
    comfyui_url: str = "http://localhost:8188"
    comfyui_timeout: int = 300

    # ── GPU ──────────────────────────────────────────────────────────────────
    gpu_count: int = 1
    gpu_vram_threshold_gb: float = 2.0

    # ── Limits ───────────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 20
    max_upload_size_mb: int = 500

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
