from __future__ import annotations

import io
import uuid
from pathlib import Path

from minio import Minio
from minio.error import S3Error

from app.config import get_settings

settings = get_settings()

_client: Minio | None = None


def get_minio_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        _ensure_buckets(_client)
    return _client


def _ensure_buckets(client: Minio) -> None:
    for bucket in (settings.minio_bucket_assets, settings.minio_bucket_output):
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)


def upload_bytes(
    data: bytes,
    filename: str,
    content_type: str,
    bucket: str | None = None,
) -> str:
    """Upload bytes to MinIO and return the storage key."""
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket_assets
    ext = Path(filename).suffix
    key = f"{uuid.uuid4().hex}{ext}"
    client.put_object(
        bucket,
        key,
        io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )
    return key


def upload_file(
    file_path: str,
    filename: str,
    content_type: str,
    bucket: str | None = None,
) -> str:
    """Upload a local file to MinIO and return the storage key."""
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket_output
    ext = Path(filename).suffix
    key = f"{uuid.uuid4().hex}{ext}"
    client.fput_object(bucket, key, file_path, content_type=content_type)
    return key


def get_presigned_url(key: str, bucket: str | None = None, expires_hours: int = 24) -> str:
    from datetime import timedelta

    client = get_minio_client()
    bucket = bucket or settings.minio_bucket_assets
    try:
        return client.presigned_get_object(bucket, key, expires=timedelta(hours=expires_hours))
    except S3Error as exc:
        raise ValueError(f"Could not generate URL for {key}: {exc}") from exc


def delete_object(key: str, bucket: str | None = None) -> None:
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket_assets
    client.remove_object(bucket, key)
