"""Provider-neutral creative generation HTTP adapter."""

from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings, get_settings


class CreativeGenerationProviderError(RuntimeError):
    """A configured generation provider rejected or could not accept a request."""


def submit_generation_request(
    *,
    provider_key: str,
    payload: dict[str, Any],
    idempotency_key: str,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Submit one provider request without interpreting or approving its output."""

    settings = settings or get_settings()
    if not settings.creative_generation_enabled:
        raise CreativeGenerationProviderError("Creative generation is disabled")
    if provider_key != "http":
        raise CreativeGenerationProviderError(f"Unsupported creative provider: {provider_key}")
    base_url = settings.creative_generation_base_url.rstrip("/")
    if not base_url or not settings.creative_generation_api_key.strip():
        raise CreativeGenerationProviderError("Creative generation endpoint or API key is missing")
    headers = {
        "authorization": f"Bearer {settings.creative_generation_api_key}",
        "idempotency-key": idempotency_key,
        "content-type": "application/json",
    }
    try:
        response = httpx.post(
            f"{base_url}/v1/generations",
            json=payload,
            headers=headers,
            timeout=settings.creative_generation_timeout_seconds,
        )
    except httpx.HTTPError as exc:
        raise CreativeGenerationProviderError(
            f"Creative generation provider request failed: {type(exc).__name__}"
        ) from exc
    if response.status_code < 200 or response.status_code >= 300:
        raise CreativeGenerationProviderError(
            f"Creative generation provider returned HTTP {response.status_code}"
        )
    try:
        result = response.json()
    except ValueError as exc:
        raise CreativeGenerationProviderError("Creative generation provider returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise CreativeGenerationProviderError("Creative generation provider returned an invalid object")
    external_request_id = str(result.get("request_id") or result.get("id") or "").strip()
    if not external_request_id:
        raise CreativeGenerationProviderError("Creative generation response has no request id")
    return {
        "external_request_id": external_request_id,
        "status": str(result.get("status") or "submitted").strip().lower(),
        "provider_response": result,
    }


__all__ = ["CreativeGenerationProviderError", "submit_generation_request"]
