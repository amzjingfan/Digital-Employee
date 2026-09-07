from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.agents.releases import publish_agent_release
from app.db.models import (
    AgentProfile,
    AgentResourceBinding,
    AgentServiceIdentity,
    BusinessResource,
    ExternalAuthorization,
    GeneralSkill,
    OrganizationMembership,
    Skill,
    Tenant,
    Tool,
    User,
)
from app.tiktok.connector import read_tiktok_resource
from app.tiktok.oauth import (
    TikTokAuthorizationStart,
    approve_mock_authorization,
    exchange_mock_authorization,
    start_mock_authorization,
)
from app.tiktok.service import (
    TIKTOK_AGENT_CATALOG,
    TIKTOK_AGENT_SKILLS,
    TIKTOK_AGENT_TOOLS,
    TIKTOK_SKILL_CATALOG,
    bootstrap_tiktok_assets,
    bootstrap_tiktok_organization,
    reconcile_casdoor_membership,
)


def test_joukir_tiktok_skill_pack_has_registry_schema_and_evals() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    registry_path = repo_root / "skills" / "joukir-tiktok-pack" / "registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    expected_ids = {skill_id for skill_id, _, _ in TIKTOK_SKILL_CATALOG}
    assert {item["skill_id"] for item in registry["skills"]} == expected_ids
    for skill_id in expected_ids:
        skill_dir = repo_root / "skills" / skill_id
        assert all(
            (skill_dir / relative_path).is_file()
            for relative_path in (
                "SKILL.md",
                "manifest.json",
                "schemas/input.json",
                "schemas/output.json",
                "references/README.md",
                "evals/cases.json",
                "LICENSES.md",
            )
        )


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id="tenant_demo", name="Demo"))
    db.commit()
    return db


def _user(user_id: str, role: str, *, account_role: str = "member") -> User:
    return User(
        id=user_id,
        tenant_id="tenant_demo",
        username=user_id,
        role=account_role,
        business_role=role,
        password_hash="disabled",
    )


def test_mock_oauth_requires_pkce_and_consumes_authorization_code_once() -> None:
    with _session() as db:
        admin = _user("admin", "member", account_role="admin")
        db.add(admin)
        db.commit()
        verifier = "v" * 64
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        request = TikTokAuthorizationStart(
            authorization_type="seller",
            subject_id="seller-demo",
            resource_id="store_tiktok_us",
            scopes=["shop.read"],
            code_challenge=challenge,
        )

        started = start_mock_authorization(db, admin, request)
        code = approve_mock_authorization(db, started.state)
        authorization = exchange_mock_authorization(db, started.state, code, verifier)

        assert authorization.provider == "tiktok"
        assert authorization.status == "active"
        assert authorization.credential_ref
        assert authorization.token_fingerprint
        assert authorization.token_fingerprint != code
        with pytest.raises(HTTPException) as reused:
            exchange_mock_authorization(db, started.state, code, verifier)
        assert reused.value.status_code == 400


def test_read_connector_rejects_wrong_scope_and_never_returns_credential(db: Session | None = None) -> None:
    close_db = db is None
    db = db or _session()
    try:
        admin = _user("admin", "member", account_role="admin")
        db.add(admin)
        db.commit()
        db.add(
            BusinessResource(
                id="store_tiktok_us",
                tenant_id="tenant_demo",
                resource_type="store",
                code="TT-US",
                name="TikTok Shop US",
                created_by_user_id=admin.id,
                metadata_json={"platform": "tiktok", "market": "US"},
            )
        )
        authorization = ExternalAuthorization(
            tenant_id="tenant_demo",
            authorization_type="seller",
            subject_id="seller-demo",
            resource_id="store_tiktok_us",
            scopes_json=["shop.read"],
            credential_ref="secret://ref-only",
            token_fingerprint="sha256:fingerprint",
        )
        db.add(authorization)
        db.commit()

        result = read_tiktok_resource(
            db,
            user=admin,
            authorization_type="seller",
            resource_id="store_tiktok_us",
            required_scope="shop.read",
        )
        assert result.source == "mock"
        assert "credential_ref" not in result.data
        assert "token_fingerprint" not in result.data
        with pytest.raises(HTTPException) as wrong_scope:
            read_tiktok_resource(
                db,
                user=admin,
                authorization_type="seller",
                resource_id="store_tiktok_us",
                required_scope="shop.write",
            )
        assert wrong_scope.value.status_code == 403
        db.add(
            BusinessResource(
                id="store_amazon_us",
                tenant_id="tenant_demo",
                resource_type="store",
                code="AMZ-US",
                name="Amazon US",
                created_by_user_id=admin.id,
                metadata_json={"platform": "amazon", "market": "US"},
            )
        )
        db.commit()
        with pytest.raises(HTTPException) as wrong_platform:
            read_tiktok_resource(
                db,
                user=admin,
                authorization_type="seller",
                resource_id="store_amazon_us",
                required_scope="shop.read",
            )
        assert wrong_platform.value.status_code == 404
    finally:
        if close_db:
            db.close()


def test_casdoor_reconciliation_keeps_one_active_primary_membership() -> None:
    with _session() as db:
        admin = _user("admin", "member", account_role="admin")
        joe = _user("joe", "tiktok_shop_operator")
        db.add(admin)
        db.add(joe)
        db.commit()
        bootstrap_tiktok_organization(db, admin)

        first = reconcile_casdoor_membership(db, joe, source="casdoor")
        assert first is not None
        assert first.business_role == "tiktok_shop_operator"
        joe.business_role = "tiktok_media_buyer"
        db.add(joe)
        db.commit()
        second = reconcile_casdoor_membership(db, joe, source="casdoor")

        memberships = db.exec(
            select(OrganizationMembership).where(
                OrganizationMembership.tenant_id == "tenant_demo",
                OrganizationMembership.user_id == joe.id,
            )
        ).all()
        assert second is not None
        assert second.business_role == "tiktok_media_buyer"
        assert [item for item in memberships if item.status == "active"] == [second]


def test_tiktok_asset_bootstrap_is_idempotent_and_binds_five_agents() -> None:
    with _session() as db:
        admin = _user("admin", "member", account_role="admin")
        db.add(admin)
        db.commit()
        bootstrap_tiktok_organization(db, admin)

        first = bootstrap_tiktok_assets(db, admin)
        agents = {row.name: row for row in db.exec(select(AgentProfile)).all()}
        skill_rows = db.exec(select(Skill)).all()
        for slug, name, _, _ in TIKTOK_AGENT_CATALOG:
            extra = next(row for row in skill_rows if row.skill_id not in TIKTOK_AGENT_SKILLS[slug])
            db.add(
                AgentResourceBinding(
                    tenant_id="tenant_demo",
                    agent_id=agents[name].id,
                    resource_type="skill",
                    resource_id=extra.id,
                    metadata_json={
                        "review_status": "approved",
                        "content_digest": "sha256:"
                        + hashlib.sha256(
                            json.dumps(
                                extra.content_json,
                                ensure_ascii=True,
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest(),
                    },
                )
            )
        db.commit()
        migrated = bootstrap_tiktok_assets(db, admin)
        second = bootstrap_tiktok_assets(db, admin)

        assert first.created_count > 0
        assert migrated.created_count == 5
        assert second.created_count == 0
        assert len(first.skill_ids) == 12
        assert len(first.agent_ids) == 5
        assert len(db.exec(select(AgentProfile)).all()) == 5
        assert len(db.exec(select(AgentServiceIdentity)).all()) == 5
        assert len(db.exec(select(GeneralSkill)).all()) == 12
        assert len(db.exec(select(Tool)).all()) >= 5
        assert len(
            db.exec(
                select(AgentResourceBinding).where(AgentResourceBinding.status == "active")
            ).all()
        ) == 53

        for slug, name, _, _ in TIKTOK_AGENT_CATALOG:
            agent = agents[name]
            bindings = db.exec(
                select(AgentResourceBinding).where(
                    AgentResourceBinding.tenant_id == "tenant_demo",
                    AgentResourceBinding.agent_id == agent.id,
                    AgentResourceBinding.status == "active",
                )
            ).all()
            active_skill_ids = {
                row.resource_id for row in bindings if row.resource_type == "skill"
            }
            active_general_skill_ids = {
                row.resource_id for row in bindings if row.resource_type == "general_skill"
            }
            active_tool_ids = {
                row.resource_id for row in bindings if row.resource_type == "tool"
            }
            expected_skill_ids = {
                row.id
                for row in db.exec(
                    select(Skill).where(
                        Skill.tenant_id == "tenant_demo",
                        Skill.skill_id.in_(tuple(TIKTOK_AGENT_SKILLS[slug])),
                    )
                ).all()
            }
            expected_general_skill_ids = {
                row.id
                for row in db.exec(
                    select(GeneralSkill).where(
                        GeneralSkill.tenant_id == "tenant_demo",
                        GeneralSkill.slug.in_(tuple(TIKTOK_AGENT_SKILLS[slug])),
                    )
                ).all()
            }
            expected_tool_ids = {
                row.id
                for row in db.exec(
                    select(Tool).where(
                        Tool.tenant_id == "tenant_demo",
                        Tool.name.in_(tuple(TIKTOK_AGENT_TOOLS[slug])),
                    )
                ).all()
            }
            assert active_skill_ids == expected_skill_ids
            assert active_general_skill_ids == expected_general_skill_ids
            assert active_tool_ids == expected_tool_ids

        inactive = db.exec(
            select(AgentResourceBinding).where(
                AgentResourceBinding.status == "inactive",
                AgentResourceBinding.resource_type == "skill",
            )
        ).all()
        assert len(inactive) == 5
        assert {
            row.metadata_json.get("deactivated_reason") for row in inactive
        } == {"outside_tiktok_agent_minimum_scope"}


def test_tiktok_production_roles_pass_business_owner_release_gate() -> None:
    with _session() as db:
        admin = _user("admin", "member", account_role="admin")
        db.add(admin)
        db.commit()
        bootstrap_tiktok_organization(db, admin)
        bootstrap_tiktok_assets(db, admin)
        agents = db.exec(select(AgentProfile)).all()
        tiktok_agents = [
            row
            for row in agents
            if str((row.metadata_json or {}).get("business_role") or "").startswith("tiktok_")
        ]
        assert len(tiktok_agents) == 5
        for agent in tiktok_agents:
            release = publish_agent_release(
                db,
                tenant_id="tenant_demo",
                agent_id=agent.id,
                actor=admin,
                reason="Business owner approval TEST-TIKTOK-001",
            )
            assert release.status == "published"
            assert agent.release_state == "published"
