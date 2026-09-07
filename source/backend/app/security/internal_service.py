from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException

from app.config import get_settings

INTERNAL_SERVICE_HEADER = "X-UltraRAG-Internal-Token"
INTERNAL_TENANT_HEADER = "X-StaffDeck-Tenant-ID"
INTERNAL_AGENT_HEADER = "X-StaffDeck-Agent-ID"
INTERNAL_SKILL_HEADER = "X-StaffDeck-Skill-ID"
INTERNAL_TOOL_HEADER = "X-StaffDeck-Tool-Name"
_INTERNAL_SERVICE_SCOPE = b"ultrarag-internal-mock-api-v1"
_INTERNAL_PRODUCTION_TOOL_SCOPE = b"staffdeck-internal-production-read-tools-v1"


def internal_service_token() -> str:
    secret = get_settings().app_secret.encode("utf-8")
    return hmac.new(secret, _INTERNAL_SERVICE_SCOPE, hashlib.sha256).hexdigest()


def internal_production_tool_token() -> str:
    """Derive a token dedicated to approved production read tools."""

    secret = get_settings().app_secret.encode("utf-8")
    return hmac.new(secret, _INTERNAL_PRODUCTION_TOOL_SCOPE, hashlib.sha256).hexdigest()


def require_internal_service(
    token: str | None = Header(default=None, alias=INTERNAL_SERVICE_HEADER),
) -> None:
    if token is None or not hmac.compare_digest(token, internal_service_token()):
        raise HTTPException(status_code=401, detail="Internal service authentication required")


def require_internal_production_tool(
    token: str | None = Header(default=None, alias=INTERNAL_SERVICE_HEADER),
) -> None:
    if token is None or not hmac.compare_digest(token, internal_production_tool_token()):
        raise HTTPException(status_code=401, detail="Production tool authentication required")
