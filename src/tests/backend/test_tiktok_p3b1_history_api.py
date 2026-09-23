from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from test_tiktok_p3b1_history import _recorded_batch, _session

from app.api.tiktok import history_import, history_workspace
from app.config import Settings
from app.db.models import User
from app.security.authorization import authorize
from app.tiktok.p3b1_history import MAX_HISTORY_REQUEST_BYTES


def _request(payload: bytes, content_type: str = "application/json") -> Request:
    async def receive():
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/enterprise/tiktok/history/import",
        "headers": [(b"content-type", content_type.encode())],
    }, receive)


def test_history_import_rejects_member_and_actual_oversize_bytes() -> None:
    with _session() as db:
        admin, recorded, run = _recorded_batch(db, "tenant_a")
        payload = json.dumps({
            "recorded_run_id": run.id,
            "source_kind": "synthetic",
            "assigned_bd_user_id": "member_tenant_a",
            "dataset": recorded.dataset.model_dump(mode="json", exclude_unset=True),
        }).encode()
        member = db.get(type(admin), "member_tenant_a")
        assert member is not None
        with pytest.raises(HTTPException) as denied:
            asyncio.run(history_import(_request(payload), current_user=member, db=db))
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as oversized:
            asyncio.run(history_import(
                _request(payload + b" " * MAX_HISTORY_REQUEST_BYTES),
                current_user=admin,
                db=db,
            ))
        assert oversized.value.status_code == 413
        assert history_workspace(current_user=admin, db=db).total_count == 0


def test_casbin_grants_bd_review_and_owner_confirm_but_not_import() -> None:
    settings = Settings(_env_file=None, casbin_enabled=True)
    with _session() as db:
        _recorded_batch(db, "tenant_a")
        bd = db.get(User, "member_tenant_a")
        assert bd is not None
        review_path = "/api/enterprise/tiktok/history/facts/fact-1/reconciliations"
        assert authorize(settings, user=bd, object_path=review_path, action="POST").allowed
        assert not authorize(settings, user=bd,
                             object_path="/api/enterprise/tiktok/history/import",
                             action="POST").allowed

        bd.business_role = "member"
        db.add(bd)
        db.commit()
        assert authorize(settings, user=bd,
                         object_path="/api/enterprise/tiktok/history/confirm",
                         action="POST").allowed
        assert not authorize(settings, user=bd, object_path=review_path,
                             action="POST").allowed
