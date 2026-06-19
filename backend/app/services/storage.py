from __future__ import annotations

import io
import shutil
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

    # Save a local copy of the converted short
    local_output_dir = Path("/app/local_outputs")
    local_output_dir.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(file_path, local_output_dir / key)
    except Exception as e:
        print(f"Warning: Could not save local copy: {e}")

    client.fput_object(bucket, key, file_path, content_type=content_type)
    return key


def get_presigned_url(key: str, bucket: str | None = None, expires_hours: int = 24) -> str:
    from datetime import timedelta
    bucket = bucket or settings.minio_bucket_assets
    try:
        # Default signing host — use settings endpoint host
        endpoint = settings.minio_endpoint
        host, sep, port = endpoint.partition(":")

        # If MinIO endpoint is an internal service name (e.g. "minio"), we
        # want the presigned URL to be valid when opened from the host
        # (browser). Sign the URL for `localhost:<port>` so requests to
        # `http://localhost:<port>/...` validate correctly.
        if host and host not in ("localhost", "127.0.0.1"):
            signing_host = "localhost"
        else:
            signing_host = host or "localhost"

        signing_endpoint = f"{signing_host}:{port}" if port else signing_host

        # Create a transient Minio client configured with the signing endpoint
        # (presigned_get_object doesn't require network access to compute the
        # signature), so the resulting URL will use the host the browser can
        # reach.
        # Provide a region to avoid an extra network call to determine it
        # (Minio will otherwise attempt to query the server for the bucket
        # region, which fails when the signing hostname is not reachable
        # from inside the container).
        temp_client = Minio(
            signing_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region="us-east-1",
        )

        url = temp_client.presigned_get_object(bucket, key, expires=timedelta(hours=expires_hours))
        return url
    except S3Error as exc:
        raise ValueError(f"Could not generate URL for {key}: {exc}") from exc


def delete_object(key: str, bucket: str | None = None) -> None:
    client = get_minio_client()
    bucket = bucket or settings.minio_bucket_assets
    client.remove_object(bucket, key)
