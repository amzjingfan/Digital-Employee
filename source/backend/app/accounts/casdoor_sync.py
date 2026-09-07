"""Periodic Casdoor Management API membership reconciliation."""

from __future__ import annotations

import json
import logging
import threading

from sqlmodel import Session

from app.accounts.casdoor import CasdoorManagementClient, CasdoorMembershipSyncResult
from app.config import Settings, get_settings
from app.db import engine, set_tenant_context

logger = logging.getLogger(__name__)
_stop_event = threading.Event()
_worker_thread: threading.Thread | None = None


def mapped_organizations(settings: Settings) -> dict[str, str]:
    try:
        payload = json.loads(settings.oidc_tenant_mapping_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OIDC tenant mapping is invalid") from exc
    if not isinstance(payload, dict):
        raise TypeError("OIDC tenant mapping is invalid")
    return {
        str(organization).strip(): str(tenant_id).strip()
        for organization, tenant_id in payload.items()
        if str(organization).strip() and str(tenant_id).strip()
    }


def reconcile_once(
    *,
    settings: Settings | None = None,
    client: CasdoorManagementClient | None = None,
    tenant_ids: set[str] | None = None,
) -> list[CasdoorMembershipSyncResult]:
    settings = settings or get_settings()
    if not settings.casdoor_management_enabled:
        return []
    organizations = {
        organization: tenant_id
        for organization, tenant_id in mapped_organizations(settings).items()
        if tenant_ids is None or tenant_id in tenant_ids
    }
    client = client or CasdoorManagementClient(settings)
    results: list[CasdoorMembershipSyncResult] = []
    for organization, tenant_id in organizations.items():
        try:
            with Session(engine) as db:
                # The runtime role is protected by PostgreSQL RLS.  A periodic
                # worker has no request-scoped dependency to establish the
                # tenant context, so bind it explicitly before reading or
                # reconciling membership rows.
                set_tenant_context(db, tenant_id)
                result = client.sync_organization_users(
                    db,
                    organization=organization,
                    tenant_id=tenant_id,
                )
            results.append(result)
            logger.info(
                "Casdoor membership reconciliation finished: organization=%s tenant=%s status=%s scanned=%d changed=%d",
                organization,
                tenant_id,
                result.status,
                result.scanned_count,
                result.changed_count,
            )
        except Exception:
            logger.exception(
                "Casdoor membership reconciliation crashed: organization=%s tenant=%s",
                organization,
                tenant_id,
            )
            results.append(
                CasdoorMembershipSyncResult(
                    "failed",
                    "casdoor_membership_reconciliation_crashed",
                )
            )
    return results


def _worker_loop(interval_seconds: float) -> None:
    while not _stop_event.is_set():
        reconcile_once()
        if _stop_event.wait(max(5.0, interval_seconds)):
            break


def start_casdoor_sync(*, interval_seconds: float | None = None) -> None:
    global _worker_thread
    settings = get_settings()
    if not settings.casdoor_management_enabled:
        return
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(
        target=_worker_loop,
        args=(interval_seconds or settings.casdoor_management_sync_interval_seconds,),
        name="casdoor-membership-reconciliation",
        daemon=True,
    )
    _worker_thread.start()


def stop_casdoor_sync() -> None:
    _stop_event.set()
    if _worker_thread and _worker_thread.is_alive():
        _worker_thread.join(timeout=2.0)
