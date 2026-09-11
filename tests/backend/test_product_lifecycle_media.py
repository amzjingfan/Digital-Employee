import base64

import httpx
import pytest

from app.config import Settings
from app.product_lifecycle.media import CreativeMediaDecodeError, inspect_creative_media
from app.product_lifecycle.storage import (
    S3CompatibleObjectStore,
    parse_s3_reference,
)


def test_png_container_is_decoded_with_dimensions() -> None:
    data = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )

    metadata = inspect_creative_media(data, "image/png")

    assert metadata["decode_status"] == "verified_container"
    assert metadata["format"] == "png"
    assert metadata["width"] == 1
    assert metadata["height"] == 1


def test_mp4_container_requires_complete_boxes() -> None:
    data = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"

    metadata = inspect_creative_media(data, "video/mp4")

    assert metadata == {
        "format": "mp4",
        "decoder_version": "joukir-media-container-v1",
        "decode_status": "verified_container",
    }


def test_media_decoder_rejects_truncated_container() -> None:
    with pytest.raises(CreativeMediaDecodeError):
        inspect_creative_media(b"\x89PNG\r\n\x1a\n", "image/png")


def test_s3_compatible_store_signs_put_and_reads_back_bytes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(
        creative_object_storage_backend="s3",
        creative_object_storage_endpoint="https://objects.example.test",
        creative_object_storage_bucket="creative-prod",
        creative_object_storage_access_key="access-test",
        creative_object_storage_secret_key="secret-must-not-be-logged",
    )
    calls: list[dict] = []

    def fake_request(method: str, url: str, **kwargs):
        calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(200, content=b"stored-bytes" if method == "GET" else b"")

    monkeypatch.setattr("app.product_lifecycle.storage.httpx.request", fake_request)
    store = S3CompatibleObjectStore(settings)

    store.put_bytes("joukir/tenant/asset.png", b"png-bytes", "image/png")
    assert store.get_bytes("joukir/tenant/asset.png") == b"stored-bytes"
    assert calls[0]["url"] == "https://objects.example.test/creative-prod/joukir/tenant/asset.png"
    assert calls[0]["headers"]["content-type"] == "image/png"
    assert "secret-must-not-be-logged" not in str(calls[0])
    assert parse_s3_reference(
        "s3://creative-prod/joukir/tenant/asset.png", "creative-prod"
    ) == "joukir/tenant/asset.png"
    assert parse_s3_reference("s3://other-bucket/asset.png", "creative-prod") is None
