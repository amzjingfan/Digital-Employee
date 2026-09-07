from __future__ import annotations

import httpx
from sqlmodel import Session, select

from app.db import engine, set_tenant_context
from app.db.models import AuthorizationDecision, User
from app.security.auth import create_access_token


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user, ttl_seconds=300)}"}


def main() -> None:
    with Session(engine) as db:
        set_tenant_context(db, "tenant_demo")
        users = db.exec(select(User).where(User.tenant_id == "tenant_demo")).all()
        admin = next(user for user in users if user.role == "admin")
        member = next(user for user in users if user.role == "member")

    with httpx.Client(base_url="http://127.0.0.1:5173", timeout=15) as client:
        member_read = client.get(
            "/api/enterprise/agents",
            params={"tenant_id": "tenant_demo"},
            headers=_headers(member),
        )
        assert member_read.status_code == 200, member_read.text

        member_write = client.delete(
            "/api/enterprise/agents/not-a-real-agent",
            params={"tenant_id": "tenant_demo"},
            headers=_headers(member),
        )
        assert member_write.status_code == 403, member_write.text
        assert member_write.json() == {"detail": "Permission denied"}

        member_audit = client.get(
            "/api/enterprise/authorization-decisions",
            headers=_headers(member),
        )
        assert member_audit.status_code == 403, member_audit.text

        admin_audit = client.get(
            "/api/enterprise/authorization-decisions",
            params={"limit": 20},
            headers=_headers(admin),
        )
        assert admin_audit.status_code == 200, admin_audit.text
        identity_roles = client.get(
            "/api/enterprise/identity-role-mappings",
            headers=_headers(admin),
        )
        assert identity_roles.status_code == 200, identity_roles.text
        identity_role_payload = identity_roles.json()
        assert identity_role_payload["group_claim"] == "groups"
        assert identity_role_payload["require_mapped_group"] is True
        assert len(identity_role_payload["roles"]) == 7
        decisions = admin_audit.json()
        denied_request_ids = {
            member_write.headers["x-request-id"],
            member_audit.headers["x-request-id"],
        }
        assert denied_request_ids.issubset({row["request_id"] for row in decisions})
        assert all(row["policy_version"] not in {"", "disabled"} for row in decisions)

        forged = User(
            id=admin.id,
            tenant_id="tenant_other",
            username=admin.username,
            role="admin",
            password_hash="disabled",
        )
        cross_tenant = client.get(
            "/api/enterprise/agents",
            params={"tenant_id": "tenant_other"},
            headers=_headers(forged),
        )
        assert cross_tenant.status_code == 401, cross_tenant.text

    with Session(engine) as db:
        set_tenant_context(db, "tenant_demo")
        stored_denials = db.exec(
            select(AuthorizationDecision).where(
                AuthorizationDecision.request_id.in_(denied_request_ids),
                AuthorizationDecision.effect == "deny",
            )
        ).all()
        assert len(stored_denials) == 2
        assert all(row.subject_id == member.id for row in stored_denials)

    print(
        "Runtime authorization verification passed: admin, member, default deny, "
        "audit evidence, identity-role catalog, and cross-tenant rejection."
    )


if __name__ == "__main__":
    main()
