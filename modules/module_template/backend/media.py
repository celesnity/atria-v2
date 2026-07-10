"""module_template S3/MinIO media store. boto3 only; never imports `atria`."""

from __future__ import annotations

import logging
import os
import uuid

import boto3
from botocore.client import Config

import db

logger = logging.getLogger("module_template.media")

MT_S3_ENDPOINT = os.environ.get("MT_S3_ENDPOINT", "http://minio:9000")
MT_S3_BUCKET = os.environ.get("MT_S3_BUCKET", "module-template")
MT_S3_ACCESS_KEY = os.environ.get("MT_S3_ACCESS_KEY", "minioadmin")
MT_S3_SECRET_KEY = os.environ.get("MT_S3_SECRET_KEY", "minioadmin")


def s3_client():
    return boto3.client(
        "s3",
        endpoint_url=MT_S3_ENDPOINT,
        aws_access_key_id=MT_S3_ACCESS_KEY,
        aws_secret_access_key=MT_S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket() -> None:
    c = s3_client()
    try:
        c.head_bucket(Bucket=MT_S3_BUCKET)
    except Exception:  # noqa: BLE001 — create when missing
        c.create_bucket(Bucket=MT_S3_BUCKET)


def put_media(filename: str, data: bytes, content_type: str = "application/octet-stream") -> dict:
    key = f"{uuid.uuid4().hex}/{filename}"
    s3_client().put_object(Bucket=MT_S3_BUCKET, Key=key, Body=data, ContentType=content_type)
    with db.db_session() as s:
        row = db.MtMedia(filename=filename, s3_key=key, content_type=content_type, size=len(data))
        s.add(row)
        s.flush()
        return row.as_dict()


def presigned_url(s3_key: str, expires: int = 3600) -> str:
    return s3_client().generate_presigned_url(
        "get_object", Params={"Bucket": MT_S3_BUCKET, "Key": s3_key}, ExpiresIn=expires
    )
