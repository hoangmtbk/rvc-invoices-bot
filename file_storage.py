import json
import logging
from io import BytesIO

from minio import Minio

from config import (
    MINIO_ACCESS_KEY,
    MINIO_BUCKET,
    MINIO_ENDPOINT,
    MINIO_PUBLIC_URL,
    MINIO_SECRET_KEY,
)

logger = logging.getLogger(__name__)

_client: Minio | None = None


def _get_client() -> Minio:
    global _client
    if _client is None:
        _client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False,
        )
    return _client


def _ensure_bucket() -> None:
    client = _get_client()
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)
        policy = json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{MINIO_BUCKET}/*"],
            }],
        })
        client.set_bucket_policy(MINIO_BUCKET, policy)
        logger.info(f"MinIO bucket '{MINIO_BUCKET}' created with public-read policy")


def build_filename(
    seller_tax_code: str, invoice_number: str, date_str: str, ext: str
) -> str:
    """Construct canonical MinIO filename."""
    tax = seller_tax_code or "unknown"
    num = invoice_number or "unknown"
    date = date_str or "00000000"
    return f"{tax}_{num}_{date}.{ext}"


def upload_file(file_bytes: bytes, filename: str, content_type: str) -> str:
    """Upload bytes to MinIO, return public HTTPS URL."""
    _ensure_bucket()
    client = _get_client()
    client.put_object(
        MINIO_BUCKET,
        filename,
        BytesIO(file_bytes),
        length=len(file_bytes),
        content_type=content_type,
    )
    url = f"{MINIO_PUBLIC_URL.rstrip('/')}/{MINIO_BUCKET}/{filename}"
    logger.info(f"Uploaded to MinIO: {filename}")
    return url
