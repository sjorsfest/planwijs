"""General-purpose Cloudflare R2 storage client.

Supports both public and private buckets with signed URL generation
for uploads and downloads.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from app.config import Settings, settings


class R2StoreError(RuntimeError):
    """Base error for R2 storage operations."""


class R2StoreConfigError(R2StoreError):
    """Raised when required R2 configuration is missing."""


class R2Store:
    """General-purpose client for Cloudflare R2 object storage."""

    def __init__(
        self,
        app_settings: Settings | None = None,
        *,
        bucket_name: str | None = None,
        public_base_url: str | None = None,
        is_private: bool = False,
    ) -> None:
        self.settings = app_settings or settings
        self.is_private = is_private

        if bucket_name:
            self.bucket_name = bucket_name
        elif is_private:
            self.bucket_name = self.settings.cloudflare_r2_private_bucket
        else:
            self.bucket_name = self.settings.cloudflare_r2_public_bucket

        self.public_base_url = public_base_url or (
            self.settings.cloudflare_r2_public_url if not is_private else None
        )

        self._client: Any | None = None

    @property
    def enabled(self) -> bool:
        required = [
            self.settings.cloudflare_r2_account_id,
            self.settings.cloudflare_r2_access_key_id,
            self.settings.cloudflare_r2_secret_access_key,
            self.bucket_name,
        ]
        return all(bool(v) for v in required)

    def build_object_key(self, *, prefix: str, filename: str) -> str:
        """Build a unique object key under a given prefix."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        nonce = secrets.token_hex(8)
        safe_name = filename.rsplit("/", 1)[-1]  # strip any path components
        return f"{prefix.strip('/')}/{timestamp}_{nonce}_{safe_name}"

    def create_signed_upload_url(
        self,
        *,
        object_key: str,
        content_type: str,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Generate a signed PUT URL for direct client-side upload.

        Returns a dict with `url`, `method`, `headers`, and `object_key`
        so the frontend can perform the upload directly.
        """
        self._validate_config()
        expires_in = int(ttl_seconds or self.settings.signed_url_ttl_seconds)
        client = self._get_client()
        assert self.bucket_name is not None

        url = client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": object_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )

        return {
            "url": url,
            "method": "PUT",
            "headers": {"Content-Type": content_type},
            "object_key": object_key,
        }

    def create_signed_download_url(
        self,
        *,
        object_key: str,
        ttl_seconds: int | None = None,
    ) -> str:
        """Generate a signed GET URL for private object access."""
        self._validate_config()
        expires_in = int(ttl_seconds or self.settings.signed_url_ttl_seconds)
        client = self._get_client()
        assert self.bucket_name is not None

        return client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket_name,
                "Key": object_key,
            },
            ExpiresIn=expires_in,
        )

    def get_public_url(self, object_key: str) -> str | None:
        """Return the public URL for an object in a public bucket."""
        if self.is_private or not self.public_base_url:
            return None
        base = self.public_base_url.rstrip("/")
        return f"{base}/{object_key}"

    def get_access_url(
        self,
        object_key: str,
        *,
        ttl_seconds: int | None = None,
    ) -> str:
        """Return the appropriate access URL: public for public buckets, signed for private."""
        if not self.is_private and self.public_base_url:
            url = self.get_public_url(object_key)
            assert url is not None
            return url
        return self.create_signed_download_url(
            object_key=object_key, ttl_seconds=ttl_seconds
        )

    def download_object(self, object_key: str) -> bytes:
        """Download an object's content from the bucket."""
        self._validate_config()
        client = self._get_client()
        assert self.bucket_name is not None
        response = client.get_object(Bucket=self.bucket_name, Key=object_key)
        return response["Body"].read()

    def delete_object(self, object_key: str) -> None:
        """Delete an object from the bucket."""
        self._validate_config()
        client = self._get_client()
        assert self.bucket_name is not None
        client.delete_object(Bucket=self.bucket_name, Key=object_key)

    def _get_client(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except Exception as exc:
            raise R2StoreConfigError(
                "boto3 is required for R2 storage operations"
            ) from exc

        assert self.settings.cloudflare_r2_account_id
        endpoint_url = f"https://{self.settings.cloudflare_r2_account_id}.r2.cloudflarestorage.com"
        return boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=self.settings.cloudflare_r2_region,
            aws_access_key_id=self.settings.cloudflare_r2_access_key_id,
            aws_secret_access_key=self.settings.cloudflare_r2_secret_access_key,
            config=Config(signature_version="s3v4"),
        )

    def _validate_config(self) -> None:
        required = {
            "cloudflare_r2_account_id": self.settings.cloudflare_r2_account_id,
            "cloudflare_r2_access_key_id": self.settings.cloudflare_r2_access_key_id,
            "cloudflare_r2_secret_access_key": self.settings.cloudflare_r2_secret_access_key,
            "bucket_name": self.bucket_name,
        }
        missing = [k for k, v in required.items() if not v]
        if missing:
            raise R2StoreConfigError(
                "Missing required R2 config: " + ", ".join(sorted(missing))
            )


# Pre-configured store instances
def get_public_store() -> R2Store:
    return R2Store(is_private=False)


def get_private_store() -> R2Store:
    return R2Store(is_private=True)
