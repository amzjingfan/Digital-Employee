"""Dependency-light creative media container inspection."""

from __future__ import annotations

import struct
import zlib
from typing import Any


class CreativeMediaDecodeError(ValueError):
    """The bytes do not contain a structurally decodable supported media file."""


def inspect_creative_media(data: bytes, content_type: str) -> dict[str, Any]:
    if content_type == "image/png":
        return _inspect_png(data)
    if content_type == "image/jpeg":
        return _inspect_jpeg(data)
    if content_type == "image/webp":
        return _inspect_webp(data)
    if content_type == "video/mp4":
        return _inspect_mp4(data)
    raise CreativeMediaDecodeError("Unsupported creative media type")


def _base(format_name: str, *, width: int | None = None, height: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "format": format_name,
        "decoder_version": "joukir-media-container-v1",
        "decode_status": "verified_container",
    }
    if width is not None:
        result["width"] = width
    if height is not None:
        result["height"] = height
    return result


def _inspect_png(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or len(data) < 33:
        raise CreativeMediaDecodeError("PNG signature or IHDR is invalid")
    width, height = struct.unpack(">II", data[16:24])
    if not width or not height or data[12:16] != b"IHDR":
        raise CreativeMediaDecodeError("PNG dimensions are invalid")
    cursor = 8
    compressed = bytearray()
    found_iend = False
    while cursor + 12 <= len(data):
        length = struct.unpack(">I", data[cursor : cursor + 4])[0]
        end = cursor + 12 + length
        if end > len(data):
            raise CreativeMediaDecodeError("PNG chunk exceeds file length")
        chunk_type = data[cursor + 4 : cursor + 8]
        chunk = data[cursor + 8 : cursor + 8 + length]
        if chunk_type == b"IDAT":
            compressed.extend(chunk)
        if chunk_type == b"IEND":
            found_iend = True
            break
        cursor = end
    if not found_iend or not compressed:
        raise CreativeMediaDecodeError("PNG is missing IDAT or IEND")
    try:
        zlib.decompress(bytes(compressed))
    except zlib.error as exc:
        raise CreativeMediaDecodeError("PNG image data cannot be decoded") from exc
    return _base("png", width=width, height=height)


def _inspect_jpeg(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9"):
        raise CreativeMediaDecodeError("JPEG start or end marker is invalid")
    cursor = 2
    while cursor + 4 <= len(data):
        if data[cursor] != 0xFF:
            cursor += 1
            continue
        marker = data[cursor + 1]
        cursor += 2
        if marker in {0xD8, 0xD9}:
            continue
        if cursor + 2 > len(data):
            break
        length = struct.unpack(">H", data[cursor : cursor + 2])[0]
        if length < 2 or cursor + length > len(data):
            raise CreativeMediaDecodeError("JPEG segment is invalid")
        if marker in set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0)):
            if length < 7:
                raise CreativeMediaDecodeError("JPEG frame header is invalid")
            height, width = struct.unpack(">HH", data[cursor + 3 : cursor + 7])
            if not width or not height:
                raise CreativeMediaDecodeError("JPEG dimensions are invalid")
            return _base("jpeg", width=width, height=height)
        cursor += length
    raise CreativeMediaDecodeError("JPEG frame header is missing")


def _inspect_webp(data: bytes) -> dict[str, Any]:
    if not data.startswith(b"RIFF") or data[8:12] != b"WEBP" or len(data) < 16:
        raise CreativeMediaDecodeError("WebP RIFF container is invalid")
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return _base("webp", width=width, height=height)
    if chunk == b"VP8L" and len(data) >= 25 and data[20] == 0x2F:
        bits = int.from_bytes(data[21:25], "little")
        width = 1 + (bits & 0x3FFF)
        height = 1 + ((bits >> 14) & 0x3FFF)
        return _base("webp", width=width, height=height)
    if chunk == b"VP8 " and len(data) >= 30 and data[23:26] == b"\x9d\x01\x2a":
        width, height = struct.unpack("<HH", data[26:30])
        return _base("webp", width=width & 0x3FFF, height=height & 0x3FFF)
    raise CreativeMediaDecodeError("WebP frame is not decodable")


def _inspect_mp4(data: bytes) -> dict[str, Any]:
    if len(data) < 12 or data[4:8] != b"ftyp":
        raise CreativeMediaDecodeError("MP4 ftyp box is missing")
    cursor = 0
    found_ftyp = False
    while cursor + 8 <= len(data):
        size = int.from_bytes(data[cursor : cursor + 4], "big")
        if size < 8 or cursor + size > len(data):
            raise CreativeMediaDecodeError("MP4 box is invalid")
        if data[cursor + 4 : cursor + 8] == b"ftyp":
            found_ftyp = True
        cursor += size
    if cursor != len(data) or not found_ftyp:
        raise CreativeMediaDecodeError("MP4 container is truncated")
    return _base("mp4")


__all__ = ["CreativeMediaDecodeError", "inspect_creative_media"]
