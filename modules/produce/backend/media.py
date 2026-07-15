"""Produce S3/MinIO media store — defect photos (P-SCRAP-03). boto3 only; never
imports minder. Reuses the shared MinIO service; owns the `produce` bucket."""

from __future__ import annotations

import logging
import os
import uuid

logger = logging.getLogger("produce.media")

PR_S3_ENDPOINT = os.environ.get("PR_S3_ENDPOINT", "http://minio:9000")
PR_S3_BUCKET = os.environ.get("PR_S3_BUCKET", "produce")
PR_S3_ACCESS_KEY = os.environ.get("PR_S3_ACCESS_KEY", "minioadmin")
PR_S3_SECRET_KEY = os.environ.get("PR_S3_SECRET_KEY", "minioadmin")


def s3_client():
    # boto3 imported lazily so `import media`/`import app` work without the S3
    # driver in the dev venv; it's only needed at actual upload time.
    import boto3
    from botocore.client import Config

    return boto3.client(
        "s3",
        endpoint_url=PR_S3_ENDPOINT,
        aws_access_key_id=PR_S3_ACCESS_KEY,
        aws_secret_access_key=PR_S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    """Create the produce bucket if missing (best-effort; no-op when MinIO absent)."""
    c = s3_client()
    try:
        c.head_bucket(Bucket=PR_S3_BUCKET)
    except Exception:  # noqa: BLE001 — create when missing
        try:
            c.create_bucket(Bucket=PR_S3_BUCKET)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ensure_bucket failed (degrading): %s", exc)


def put_defect_photo(
    scrap_id: int, filename: str, data: bytes, content_type: str = "image/jpeg"
) -> str:
    """Upload a defect photo and return its S3 key (stored as scrap.photo_ref)."""
    key = f"scrap/{scrap_id}/{uuid.uuid4().hex}-{filename}"
    s3_client().put_object(Bucket=PR_S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    return key


def presigned_url(s3_key: str, expires: int = 3600) -> str:
    return s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": PR_S3_BUCKET, "Key": s3_key}, ExpiresIn=expires
    )
