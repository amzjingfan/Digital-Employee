from __future__ import annotations

import httpx
from sqlmodel import Session

from app.db import engine, set_tenant_context
from app.db.models import User
from app.security.auth import create_access_token

ROLE_KEYS = (
    "operations_supervisor",
    "after_sales_specialist",
    "listing_compliance_specialist",
    "logistics_exception_specialist",
    "advertising_inspection_specialist",
    "designer",
    "procurement_specialist",
)


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user, ttl_seconds=300)}"}


def main() -> None:
    test_cases = []
    for role in ROLE_KEYS:
        user = User(
            id=f"verify_role_{role}",
            tenant_id="tenant_demo",
            username=f"verify-{role}",
            role="member",
            business_role=role,
            authorization_source="oidc_groups",
            identity_groups_json=[f"九头蛇/staffdeck-jiutoushe-verify-{role}"],
            source="oidc",
            password_hash="disabled",
        )
        test_cases.append((role, user.id, user, _headers(user)))

    with Session(engine) as db:
        set_tenant_context(db, "tenant_demo")
        for _role, user_id, user, _headers_value in test_cases:
            stale = db.get(User, user_id)
            if stale:
                db.delete(stale)
                db.flush()
            db.add(user)
        db.commit()

    try:
        with httpx.Client(base_url="http://127.0.0.1:5173", timeout=15) as client:
            for role, _user_id, _user, headers in test_cases:
                allowed = client.get(
                    "/api/enterprise/agents",
                    params={"tenant_id": "tenant_demo"},
                    headers=headers,
                )
                assert allowed.status_code == 200, (role, allowed.text)

                privileged = client.get(
                    "/api/enterprise/identity-role-mappings",
                    headers=headers,
                )
                assert privileged.status_code == 403, (role, privileged.text)

            procurement_delete = client.delete(
                "/api/enterprise/tools/not-a-real-tool",
                params={"tenant_id": "tenant_demo"},
                headers=test_cases[-1][3],
            )
            assert procurement_delete.status_code == 403, procurement_delete.text
    finally:
        with Session(engine) as db:
            set_tenant_context(db, "tenant_demo")
            for _role, user_id, _user, _headers_value in test_cases:
                persisted = db.get(User, user_id)
                if persisted:
                    db.delete(persisted)
            db.commit()

    print(
        "Runtime business-role verification passed: seven roles, allowed operational reads, "
        "privileged-page denial, and sensitive-write denial."
    )


if __name__ == "__main__":
    main()
