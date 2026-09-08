"""S3-compatible object storage seam for production creative files."""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime
from urllib.parse import quote, urlsplit

import httpx

from app.config import Settings, get_settings


class ObjectStorageError(RuntimeError):
    """A storage operation failed without exposing credentials or response bodies."""


class S3CompatibleObjectStore:
    """Small path-style S3 client using the existing httpx dependency.

    Keeping this adapter narrow avoids adding a provider SDK to the desktop
    bundle. S3, MinIO and compatible gateways can use the same signed seam.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        missing = [
            name
            for name, value in {
                "endpoint": self.settings.creative_object_storage_endpoint,
                "bucket": self.settings.creative_object_storage_bucket,
                "access_key": self.settings.creative_object_storage_access_key,
                "secret_key": self.settings.creative_object_storage_secret_key,
            }.items()
            if not str(value).strip()
        ]
        if missing:
            raise ObjectStorageError(
                "Creative object storage is not configured: " + ", ".join(missing)
            )
        parsed = urlsplit(self.settings.creative_object_storage_endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ObjectStorageError("Creative object storage endpoint must be an HTTP URL")

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self._request("PUT", key, data, content_type=content_type)

    def get_bytes(self, key: str) -> bytes:
        return self._request("GET", key).content

    def _request(
        self,
        method: str,
        key: str,
        data: bytes = b"",
        *,
        content_type: str = "application/octet-stream",
    ) -> httpx.Response:
        normalized_key = "/".join(part for part in key.strip("/").split("/") if part)
        if not normalized_key or ".." in normalized_key.split("/"):
            raise ObjectStorageError("Object key is invalid")
        endpoint = self.settings.creative_object_storage_endpoint.rstrip("/")
        path = f"/{quote(self.settings.creative_object_storage_bucket, safe='')}/{quote(normalized_key, safe='/')}"
        url = f"{endpoint}{path}"
        parsed = urlsplit(url)
        payload_hash = hashlib.sha256(data).hexdigest()
        now = datetime.now(UTC)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        headers = {
            "host": parsed.netloc,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        if method == "PUT":
            headers["content-type"] = content_type
        if self.settings.creative_object_storage_session_token:
            headers["x-amz-security-token"] = self.settings.creative_object_storage_session_token
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in sorted(headers))
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join(
            [
                method,
                path,
                "",
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        scope = f"{date_stamp}/{self.settings.creative_object_storage_region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _signing_key(
            self.settings.creative_object_storage_secret_key,
            date_stamp,
            self.settings.creative_object_storage_region,
        )
        signature = hmac.new(signing_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()
        headers["authorization"] = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self.settings.creative_object_storage_access_key}/{scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        try:
            response = httpx.request(
                method,
                url,
                headers=headers,
                content=data if method == "PUT" else None,
                timeout=self.settings.creative_object_storage_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise ObjectStorageError(f"Creative object storage request failed: {type(exc).__name__}") from exc
        if response.status_code < 200 or response.status_code >= 300:
            raise ObjectStorageError(
                f"Creative object storage returned HTTP {response.status_code}"
            )
        return response


def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    date_key = hmac.new(f"AWS4{secret}".encode("utf-8"), date_stamp.encode("utf-8"), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def configured_object_store(settings: Settings | None = None) -> S3CompatibleObjectStore | None:
    settings = settings or get_settings()
    if settings.creative_object_storage_backend.strip().lower() != "s3":
        return None
    return S3CompatibleObjectStore(settings)


def parse_s3_reference(reference: str, expected_bucket: str) -> str | None:
    """Extract a safe key from s3://bucket/key without accepting another bucket."""

    if not reference.startswith("s3://"):
        return None
    bucket_and_key = reference.removeprefix("s3://")
    bucket, separator, key = bucket_and_key.partition("/")
    if not separator or bucket != expected_bucket or not key or ".." in key.split("/"):
        return None
    return key


__all__ = [
    "ObjectStorageError",
    "S3CompatibleObjectStore",
    "configured_object_store",
    "parse_s3_reference",
]
