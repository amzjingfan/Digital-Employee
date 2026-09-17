from __future__ import annotations

import argparse
import hashlib

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from app.agents.branching import (
    visible_knowledge_base_versions,
    visible_published_skills,
    visible_tool_rows,
)
from app.config import get_settings
from app.db.database import engine, set_tenant_context
from app.db.models import AgentServiceIdentity
from app.work_tasks.m2m import authenticate_service_identity, clear_service_token_cache


def compact(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify role-isolated Casdoor M2M identities")
    parser.add_argument("--tenant-id", default="tenant_demo")
    parser.add_argument(
        "--expected-count",
        type=int,
        default=12,
        help="expected active identity count; P3-A defaults to 7 legacy + 5 TikTok roles",
    )
    args = parser.parse_args()
    settings = get_settings()
    clear_service_token_cache()
    with Session(engine) as db:
        set_tenant_context(db, args.tenant_id)
        identities = db.exec(
            select(AgentServiceIdentity)
            .where(AgentServiceIdentity.tenant_id == args.tenant_id)
            .order_by(AgentServiceIdentity.business_role)
        ).all()
        resource_counts = {
            identity.id: (
                len(visible_published_skills(db, args.tenant_id, identity.agent_id)),
                len(
                    visible_knowledge_base_versions(
                        db, args.tenant_id, identity.agent_id, include_inactive=False
                    )
                ),
                len(
                    visible_tool_rows(
                        db, args.tenant_id, identity.agent_id, include_inactive=False
                    )
                ),
            )
            for identity in identities
        }
    if len(identities) != args.expected_count:
        raise RuntimeError(
            f"Expected {args.expected_count} service identities, found {len(identities)}"
        )
    if len({item.agent_id for item in identities}) != args.expected_count:
        raise RuntimeError("Service identities are not bound one-to-one to digital employees")
    if len({item.client_id for item in identities}) != args.expected_count:
        raise RuntimeError("Casdoor client IDs are not unique per role")
    for identity in identities:
        receipt = authenticate_service_identity(identity, settings)
        if identity.client_id not in receipt.audience:
            raise RuntimeError(f"Unexpected token audience for role {identity.business_role}")
        sops, knowledge, tools = resource_counts[identity.id]
        print(
            f"verified role={identity.business_role} app={identity.application_name} "
            f"subject_fp={compact(receipt.subject)} token_fp={compact(receipt.token_fingerprint)} "
            f"sops={sops} knowledge={knowledge} tools={tools}"
        )
    forbidden_columns = {"client_secret", "access_token", "refresh_token", "id_token"}
    persisted_columns = {
        str(item["name"]) for item in inspect(engine).get_columns("agent_service_identities")
    }
    if forbidden_columns & persisted_columns:
        raise RuntimeError("StaffDeck service-identity schema contains token or secret columns")
    with Session(engine) as db:
        if db.exec(select(AgentServiceIdentity)).first() is not None:
            raise RuntimeError("RLS exposed service identities without tenant context")
    with Session(engine) as db:
        set_tenant_context(db, "tenant-not-authorized")
        if db.exec(select(AgentServiceIdentity)).first() is not None:
            raise RuntimeError("RLS exposed service identities to another tenant context")
    target_id = identities[0].id
    with Session(engine) as db:
        set_tenant_context(db, args.tenant_id)
        try:
            db.exec(
                text(
                    "UPDATE agent_service_identities SET client_id = client_id WHERE id = :id"
                ).bindparams(id=target_id)
            )
            db.commit()
        except DBAPIError:
            db.rollback()
        else:
            raise RuntimeError("Runtime role can mutate protected service-identity configuration")
    with Session(engine) as db:
        set_tenant_context(db, args.tenant_id)
        db.exec(
            text(
                "UPDATE agent_service_identities "
                "SET last_error_code = last_error_code WHERE id = :id"
            ).bindparams(id=target_id)
        )
        db.commit()
    print(
        f"verified={args.expected_count} distinct_agents={args.expected_count} "
        f"distinct_clients={args.expected_count} secrets_printed=0 tokens_printed=0"
    )
    print("rls=no_context_denied,cross_tenant_denied protected_columns=denied receipt_columns=allowed")


if __name__ == "__main__":
    main()
