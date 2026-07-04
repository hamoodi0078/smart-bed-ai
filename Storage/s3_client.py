"""AWS S3 client for Smart Bed AI.

Handles uploading reports, audio recordings, and user backups to S3,
and generating pre-signed download URLs.

Public API
----------
S3Client(bucket, region, access_key, secret_key)
    .upload_bytes(key, data, content_type)   -> str   (S3 URI)
    .upload_file(key, local_path)            -> str   (S3 URI)
    .download_bytes(key)                     -> bytes
    .presigned_url(key, expires_in)          -> str   (HTTPS URL)
    .delete(key)                             -> bool
    .key_exists(key)                         -> bool

build_s3_client_from_settings()             -> S3Client | None
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("Storage.s3_client")

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    _BOTO3_AVAILABLE = True
except ImportError:
    _BOTO3_AVAILABLE = False


class S3Client:
    """Thin wrapper around boto3 S3 with graceful error handling."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str = "us-east-1",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        if not _BOTO3_AVAILABLE:
            raise RuntimeError("boto3 is not installed — pip install boto3")

        self._bucket = str(bucket).strip()
        self._region = str(region).strip() or "us-east-1"

        session_kwargs: dict[str, Any] = {}
        if access_key and secret_key:
            session_kwargs["aws_access_key_id"] = access_key
            session_kwargs["aws_secret_access_key"] = secret_key

        self._s3 = boto3.client("s3", region_name=self._region, **session_kwargs)

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """Upload raw bytes to S3. Returns the s3:// URI."""
        self._s3.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )
        uri = f"s3://{self._bucket}/{key}"
        logger.info("Uploaded %d bytes → %s", len(data), uri)
        return uri

    def upload_file(self, key: str, local_path: str | Path) -> str:
        """Upload a local file to S3. Returns the s3:// URI."""
        local_path = Path(local_path)
        self._s3.upload_file(str(local_path), self._bucket, key)
        uri = f"s3://{self._bucket}/{key}"
        logger.info("Uploaded file %s → %s", local_path.name, uri)
        return uri

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def download_bytes(self, key: str) -> bytes:
        """Download an S3 object and return its content as bytes."""
        response = self._s3.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    # ------------------------------------------------------------------
    # Presigned URL
    # ------------------------------------------------------------------

    def presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned GET URL valid for *expires_in* seconds."""
        url: str = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=int(expires_in),
        )
        return url

    # ------------------------------------------------------------------
    # Delete / exists
    # ------------------------------------------------------------------

    def delete(self, key: str) -> bool:
        """Delete an S3 object. Returns True on success."""
        try:
            self._s3.delete_object(Bucket=self._bucket, Key=key)
            logger.info("Deleted s3://%s/%s", self._bucket, key)
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.warning("S3 delete failed key=%s error=%s", key, exc)
            return False

    def key_exists(self, key: str) -> bool:
        """Return True if the object exists in the bucket."""
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "404":
                return False
            raise


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_s3_client_from_settings() -> "S3Client | None":
    """Build an S3Client from config/settings.py.  Returns None if not configured."""
    if not _BOTO3_AVAILABLE:
        logger.warning("boto3 not installed — S3 unavailable")
        return None

    try:
        from config.settings import settings

        bucket = str(getattr(settings, "aws_s3_bucket", "") or "").strip()
        if not bucket:
            return None
        return S3Client(
            bucket=bucket,
            region=str(getattr(settings, "aws_region", "us-east-1") or "us-east-1"),
            access_key=str(getattr(settings, "aws_access_key_id", "") or ""),
            secret_key=str(getattr(settings, "aws_secret_access_key", "") or ""),
        )
    except Exception as exc:
        logger.warning("S3 client init failed: %s", exc)
        return None
