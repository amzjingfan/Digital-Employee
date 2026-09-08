"""Safe local status checks for the DesignKit CLI dependency."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.db.models import User
from app.security.auth import ensure_current_user_tenant, get_current_user
from app.security.tenant import ensure_tenant


class DesignKitCliStatusRead(BaseModel):
    installed: bool
    command: str | None = None
    version: str | None = None
    minimum_version: str = "1.0.24"
    version_supported: bool = False
    local_config_dir_present: bool = False
    mcp_protocol_exposed: bool = False


router = APIRouter(
    prefix="/api/enterprise/designkit-cli",
    tags=["enterprise:designkit"],
    dependencies=[Depends(get_current_user)],
)


def _find_command() -> str | None:
    for candidate in ("designkit.cmd", "designkit.exe", "designkit"):
        command = shutil.which(candidate)
        if command:
            return command
    return None


def _version_tuple(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", value)
    return tuple(int(part) for part in match.groups()) if match else None


def _read_cli_version(command: str) -> str | None:
    try:
        result = subprocess.run(
            [command, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (result.stdout or result.stderr or "").strip()
    return output.splitlines()[0][:80] if result.returncode == 0 and output else None


@router.get("/status", response_model=DesignKitCliStatusRead)
def designkit_cli_status(
    tenant_id: str = Query(...),
    db: Session = Depends(get_session),  # noqa: B008
    current_user: User = Depends(get_current_user),  # noqa: B008
) -> DesignKitCliStatusRead:
    ensure_tenant(db, tenant_id)
    ensure_current_user_tenant(tenant_id, current_user)
    command = _find_command()
    version = _read_cli_version(command) if command else None
    parsed = _version_tuple(version)
    minimum = _version_tuple("1.0.24")
    return DesignKitCliStatusRead(
        installed=command is not None,
        command=command,
        version=version,
        version_supported=bool(parsed and minimum and parsed >= minimum),
        local_config_dir_present=(Path.home() / ".designkit").is_dir(),
        # The installed CLI is not an MCP server.  Keeping this explicit
        # prevents the UI from implying that a local CLI can be saved as MCP.
        mcp_protocol_exposed=False,
    )
