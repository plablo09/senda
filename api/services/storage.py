from __future__ import annotations
import pathlib
import re
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from api.config import settings


def _sanitize_filename(filename: str) -> str:
    """Strip directory components and replace unsafe characters."""
    name = pathlib.Path(filename).name
    name = re.sub(r"[^a-zA-Z0-9._-]", "_", name)
    return name or "file"

def get_s3_client() -> boto3.client:
    return boto3.client(
        "s3",
        endpoint_url=settings.storage_endpoint,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",  # required by boto3, value doesn't matter for MinIO
    )

def ensure_bucket_exists() -> None:
    """Create the bucket if it doesn't exist. Safe to call on startup."""
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=settings.storage_bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("404", "NoSuchBucket"):
            client.create_bucket(Bucket=settings.storage_bucket)
        else:
            raise

def upload_html(documento_id: str, html_content: bytes) -> str:
    """Upload rendered HTML and return the public URL."""
    client = get_s3_client()
    key = f"documentos/{documento_id}/index.html"
    client.put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=html_content,
        ContentType="text/html; charset=utf-8",
    )
    return f"{settings.storage_public_endpoint}/{settings.storage_bucket}/{key}"


def upload_dataset(dataset_id: str, filename: str, content: bytes, mimetype: str) -> str:
    """Upload a dataset file and return the public URL."""
    client = get_s3_client()
    safe_name = _sanitize_filename(filename)
    key = f"datasets/{dataset_id}/{safe_name}"
    client.put_object(
        Bucket=settings.storage_bucket,
        Key=key,
        Body=content,
        ContentType=mimetype,
    )
    return f"{settings.storage_public_endpoint}/{settings.storage_bucket}/{key}"


def delete_object(key: str) -> None:
    """Delete an object from storage by key."""
    client = get_s3_client()
    client.delete_object(Bucket=settings.storage_bucket, Key=key)
