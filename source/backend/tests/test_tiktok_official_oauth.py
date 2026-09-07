from __future__ import annotations

import json

import httpx
import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import Settings
from app.db.models import (
    BusinessResource,
    BusinessResourceScope,
    ConnectorSyncState,
    ExternalAuthorization,
    Tenant,
    User,
)
from app.tiktok.connector import read_tiktok_resource
from app.tiktok.official import (
    FileTokenStore,
    TikTokOfficialClient,
    TikTokOfficialError,
    exchange_official_authorization,
    sign_tiktok_request,
    start_official_authorization,
)
from app.tiktok.schema import TikTokOfficialAuthorizationStart


def _session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    db = Session(engine)
    db.add(Tenant(id="tenant_demo", name="Demo"))
    db.add(
        User(
            id="admin",
            tenant_id="tenant_demo",
            username="admin",
            role="admin",
            business_role="platform_admin",
            password_hash="disabled",
        )
    )
    db.commit()
    return db


def _settings(store_path: str) -> Settings:
    return Settings(
        _env_file=None,
        app_secret="local-test-app-secret",
        tiktok_official_enabled=True,
        tiktok_app_key="app-key",
        tiktok_app_secret="app-secret",
        tiktok_service_id="service-id",
        tiktok_redirect_uri="http://localhost:5173/api/enterprise/tiktok/authorizations/official/callback",
        tiktok_market="US",
        tiktok_token_store_file=store_path,
    )


def test_tiktok_request_signature_matches_official_hmac_shape() -> None:
    assert (
        sign_tiktok_request(
            path="/authorization/202309/shops",
            query={"timestamp": "1623812664", "app_key": "123456"},
            app_secret="abc000def111",
        )
        == "d1e628c7f4f1e24a79acfba00113d853cba9c734228a95eae62b4ef57b8c4dd9"
    )


def test_official_authorization_requires_distinct_service_id(tmp_path) -> None:
    settings = _settings(str(tmp_path / "tokens.json"))
    settings.tiktok_service_id = ""

    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        with pytest.raises(TikTokOfficialError) as error:
            start_official_authorization(
                db,
                admin,
                TikTokOfficialAuthorizationStart(
                    authorization_type="seller",
                    market="US",
                    scopes=["seller.shop.info"],
                ),
                settings=settings,
            )

    assert error.value.code == "tiktok_service_id_missing"


def test_official_oauth_exchanges_code_stores_tokens_outside_database_and_seeds_shop_scope(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/api/v2/token/get"):
            assert request.url.params["grant_type"] == "authorized_code"
            assert request.url.params["app_key"] == "app-key"
            assert request.url.params["app_secret"] == "app-secret"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "access_token": "access-token-real",
                        "access_token_expire_in": 4102444800,
                        "refresh_token": "refresh-token-real",
                        "refresh_token_expire_in": 4102444800,
                        "open_id": "open-seller-1",
                        "seller_name": "Demo Shop",
                        "seller_base_region": "US",
                        "user_type": 0,
                        "granted_scopes": ["seller.shop.info"],
                    },
                },
            )
        assert request.url.host == "open-api.tiktokglobalshop.com"
        assert request.url.path == "/authorization/202309/shops"
        assert request.headers["x-tts-access-token"] == "access-token-real"
        assert request.url.params["sign"]
        return httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "shops": [
                        {
                            "shop_id": "shop-us-1",
                            "shop_name": "Demo Shop",
                            "shop_cipher": "cipher-us-1",
                            "region": "US",
                        }
                    ]
                },
            },
        )

    settings = _settings(str(tmp_path / "tiktok-tokens.json"))
    client = TikTokOfficialClient(settings, transport=httpx.MockTransport(handler))
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        started = start_official_authorization(
            db,
            admin,
            TikTokOfficialAuthorizationStart(
                authorization_type="seller",
                market="US",
                scopes=["seller.shop.info"],
            ),
            settings=settings,
        )
        assert "app_secret" not in started.authorize_url
        assert "service_id=service-id" in started.authorize_url

        authorizations = exchange_official_authorization(
            db,
            admin,
            state=started.state,
            code="official-auth-code",
            client=client,
        )

        assert len(authorizations) == 1
        authorization = authorizations[0]
        assert authorization.subject_id == "open-seller-1"
        assert authorization.resource_id == "tiktok_shop_shop-us-1"
        assert authorization.metadata_json["authorization_flow"] == "official"
        assert authorization.credential_ref.startswith("secret://tiktok/")
        assert "access-token-real" not in json.dumps(authorization.model_dump(), default=str)
        resource = db.get(BusinessResource, authorization.resource_id)
        assert resource is not None
        assert resource.metadata_json["shop_cipher"] == "cipher-us-1"
        scopes = db.exec(
            select(BusinessResourceScope).where(
                BusinessResourceScope.resource_id == resource.id,
            )
        ).all()
        assert {(row.business_role, row.access_level) for row in scopes} == {
            ("operations_supervisor", "viewer"),
            ("tiktok_shop_operator", "viewer"),
        }

    stored = json.loads((tmp_path / "tiktok-tokens.json").read_text(encoding="utf-8"))
    serialized = json.dumps(stored)
    assert "access-token-real" not in serialized
    assert "refresh-token-real" not in serialized
    assert len(requests) == 2


def test_file_token_store_round_trips_encrypted_values(tmp_path) -> None:
    path = tmp_path / "tokens.json"
    store = FileTokenStore(
        path,
        encrypt=lambda value: f"enc:{value}",
        decrypt=lambda value: value.removeprefix("enc:"),
    )
    store.put("secret://tiktok/tenant/ref", {"access_token": "access", "refresh_token": "refresh"})
    assert store.get("secret://tiktok/tenant/ref") == {
        "access_token": "access",
        "refresh_token": "refresh",
    }


def test_official_connector_reads_only_sanitized_permission_summary(monkeypatch) -> None:
    class FakeOfficialClient:
        def get_seller_permissions(self, credential_ref: str) -> dict[str, object]:
            assert credential_ref == "secret://tiktok/tenant/ref"
            return {"permissions": [{"name": "seller.shop.info"}], "access_token": "must-not-leak"}

    monkeypatch.setattr("app.tiktok.connector.TikTokOfficialClient", FakeOfficialClient)
    with _session() as db:
        admin = db.get(User, "admin")
        assert admin is not None
        db.add(
            BusinessResource(
                id="tiktok_shop_shop-us-1",
                tenant_id="tenant_demo",
                resource_type="store",
                code="shop-us-1",
                name="Demo Shop",
                created_by_user_id=admin.id,
                metadata_json={"platform": "tiktok", "market": "US"},
            )
        )
        db.add(
            ExternalAuthorization(
                tenant_id="tenant_demo",
                provider="tiktok",
                authorization_type="seller",
                subject_id="open-seller-1",
                resource_id="tiktok_shop_shop-us-1",
                scopes_json=["seller.shop.info"],
                credential_ref="secret://tiktok/tenant/ref",
                token_fingerprint="sha256:fingerprint",
                metadata_json={
                    "authorization_flow": "official",
                    "official_scopes": ["seller.shop.info"],
                },
            )
        )
        db.commit()
        result = read_tiktok_resource(
            db,
            user=admin,
            authorization_type="seller",
            resource_id="tiktok_shop_shop-us-1",
            required_scope="shop.read",
        )

        assert result.source == "official"
        assert result.data["permission_count"] == 1
        assert "access_token" not in result.data
        sync = db.exec(select(ConnectorSyncState)).one()
        assert sync.connector_type == "tiktok.official.seller"
