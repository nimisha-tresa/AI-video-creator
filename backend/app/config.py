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
    auth_bypass_enabled: bool = False
    auth_bypass_email: str = "dev@local.app"
    auth_bypass_username: str = "dev_bypass"
    auth_bypass_superuser: bool = True

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str
    db_auto_create_schema: bool = True
    db_auto_create_schema_in_production: bool = False

    # ── Redis / Celery ───────────────────────────────────────────────────────
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # ── MinIO / S3 ───────────────────────────────────────────────────────────
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin123"
    minio_bucket_assets: str = "assets"
    minio_bucket_output: str = "output"
    minio_secure: bool = False

    # ── ComfyUI ──────────────────────────────────────────────────────────────
    comfyui_url: str = "http://comfyui:8188"
    comfyui_timeout: int = 180
    comfyui_engine: str = "auto"

    # ── Pollinations (cloud video fallback) ───────────────────────────────────
    pollinations_api_key: str = ""

    @property
    def true_video_enabled(self) -> bool:
        return bool(self.pollinations_api_key.strip())

    # ── Local storage (development) ──────────────────────────────────────────
    # Directory inside the `api`/`worker` container where outputs will be
    # written and served by the API. This path is relative to the application
    # root ("/app"). For host access, the backend source is bind-mounted so
    # files here appear under the repo's `backend/` directory on the host.
    local_output_dir: str = "storage/output"
    api_base_url: str = "http://localhost:8000"
    # Used by worker/ComfyUI to fetch uploaded assets inside Docker network
    internal_api_url: str = "http://api:8000"

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
