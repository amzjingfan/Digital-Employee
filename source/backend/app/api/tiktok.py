from __future__ import annotations

from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.agents.releases import AgentReleaseError
from app.db import get_session
from app.db.models import TikTokOAuthState, User
from app.security.auth import get_current_user
from app.tiktok.connector import TikTokConnectorRead, read_tiktok_resource
from app.tiktok.mock_replay import (
    execute_tiktok_mock_replays,
    persist_tiktok_mock_replay_tasks,
    run_tiktok_mock_sop_exception_matrix,
    run_tiktok_mock_sop_replays,
)
from app.tiktok.oauth import (
    TikTokAuthorizationStart,
    TikTokAuthorizationStartResponse,
    approve_mock_authorization,
    exchange_mock_authorization,
    start_mock_authorization,
    state_hash,
)
from app.tiktok.official import (
    TikTokOfficialError,
    exchange_official_authorization,
    start_official_authorization,
)
from app.tiktok.schema import (
    TikTokAgentReleasePreflight,
    TikTokAgentReleasePublishRequest,
    TikTokAgentReleasePublishResult,
    TikTokAssetBootstrapResponse,
    TikTokAuthorizationExchange,
    TikTokAuthorizationRead,
    TikTokBootstrapResponse,
    TikTokM2MVerificationResponse,
    TikTokMembershipReconcileResponse,
    TikTokMockReplayExecutionResponse,
    TikTokMockReplayRequest,
    TikTokOfficialAuthorizationStart,
    TikTokOverview,
    TikTokProductionReadiness,
    TikTokShadowEvaluationCreate,
    TikTokShadowEvaluationRead,
    TikTokShadowRunRead,
)
from app.tiktok.service import (
    TikTokAgentReleaseGateError,
    bootstrap_tiktok_assets,
    bootstrap_tiktok_organization,
    get_tiktok_agent_release_preflight,
    get_tiktok_overview,
    get_tiktok_production_readiness,
    publish_tiktok_agent_releases,
    reconcile_casdoor_memberships,
    verify_tiktok_m2m_identities,
)
from app.tiktok.shadow import (
    TikTokShadowError,
    get_shadow_quality,
    get_shadow_run,
    heartbeat_shadow_run,
    record_shadow_evaluation,
    start_shadow_run,
)

router = APIRouter(prefix="/api/enterprise/tiktok", tags=["enterprise-tiktok"])


@router.get("/overview", response_model=TikTokOverview)
def overview(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokOverview:
    return get_tiktok_overview(db, current_user)


@router.get("/production-readiness", response_model=TikTokProductionReadiness)
def production_readiness(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokProductionReadiness:
    return get_tiktok_production_readiness(db, current_user)


@router.get("/release-preflight", response_model=TikTokAgentReleasePreflight)
def release_preflight(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokAgentReleasePreflight:
    return get_tiktok_agent_release_preflight(db, current_user)


@router.post("/releases/publish", response_model=TikTokAgentReleasePublishResult)
def publish_releases(
    request: TikTokAgentReleasePublishRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokAgentReleasePublishResult:
    try:
        return publish_tiktok_agent_releases(db, current_user, request.approval_reference)
    except TikTokAgentReleaseGateError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "tiktok_agent_release_preflight_failed",
                "message": str(exc),
                "checks": [item.model_dump() for item in exc.checks],
            },
        ) from exc
    except AgentReleaseError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/m2m/verify", response_model=TikTokM2MVerificationResponse)
def verify_m2m_identities(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokM2MVerificationResponse:
    return verify_tiktok_m2m_identities(db, current_user)


@router.post("/mock-sop-replays/run", response_model=dict)
def run_mock_sop_replays(
    request: TikTokMockReplayRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    # Keep the acceptance harness behind the same tenant-admin boundary as
    # production gates. It is deliberately side-effect free and never uses the DB.
    from app.security.permissions import ensure_tenant_admin

    ensure_tenant_admin(current_user.tenant_id, current_user)
    return (
        persist_tiktok_mock_replay_tasks(db, current_user)
        if request.persist
        else run_tiktok_mock_sop_replays()
    )


@router.get("/mock-sop-replays/exception-matrix", response_model=dict)
def mock_sop_exception_matrix(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> dict:
    from app.security.permissions import ensure_tenant_admin

    ensure_tenant_admin(current_user.tenant_id, current_user)
    return run_tiktok_mock_sop_exception_matrix()


@router.post(
    "/mock-sop-replays/execute-sandbox",
    response_model=TikTokMockReplayExecutionResponse,
)
def execute_mock_sop_replays(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokMockReplayExecutionResponse:
    from app.security.permissions import ensure_tenant_admin

    ensure_tenant_admin(current_user.tenant_id, current_user)
    return TikTokMockReplayExecutionResponse.model_validate(
        execute_tiktok_mock_replays(db, current_user)
    )


@router.post("/bootstrap", response_model=TikTokBootstrapResponse)
def bootstrap(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokBootstrapResponse:
    organization = bootstrap_tiktok_organization(db, current_user)
    organization.assets = bootstrap_tiktok_assets(db, current_user)
    return organization


@router.post("/bootstrap-assets", response_model=TikTokAssetBootstrapResponse)
def bootstrap_assets(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokAssetBootstrapResponse:
    return bootstrap_tiktok_assets(db, current_user)


@router.post("/memberships/reconcile", response_model=TikTokMembershipReconcileResponse)
def reconcile_memberships(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokMembershipReconcileResponse:
    return TikTokMembershipReconcileResponse(
        reconciled_count=reconcile_casdoor_memberships(db, current_user)
    )


@router.post("/shadow/start", response_model=TikTokShadowRunRead)
def shadow_start(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokShadowRunRead:
    try:
        run = start_shadow_run(db, current_user)
    except TikTokShadowError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _shadow_read(db, run)


@router.get("/shadow/status", response_model=TikTokShadowRunRead | None)
def shadow_status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokShadowRunRead | None:
    return _shadow_read(db, get_shadow_run(db, current_user.tenant_id))


@router.post("/shadow/heartbeat", response_model=TikTokShadowRunRead | None)
def shadow_heartbeat(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokShadowRunRead | None:
    return _shadow_read(db, heartbeat_shadow_run(db, current_user.tenant_id))


@router.post("/shadow/evaluations", response_model=TikTokShadowEvaluationRead)
def shadow_evaluate(
    request: TikTokShadowEvaluationCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokShadowEvaluationRead:
    try:
        return record_shadow_evaluation(db, current_user, request)
    except TikTokShadowError as exc:
        status_code = 403 if current_user.role != "admin" else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc


@router.post("/authorizations/start", response_model=TikTokAuthorizationStartResponse)
def authorization_start(
    request: TikTokAuthorizationStart,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokAuthorizationStartResponse:
    return start_mock_authorization(db, current_user, request)


@router.post("/authorizations/official/start", response_model=TikTokAuthorizationStartResponse)
def official_authorization_start(
    request: TikTokOfficialAuthorizationStart,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokAuthorizationStartResponse:
    try:
        return start_official_authorization(db, current_user, request)
    except TikTokOfficialError as exc:
        raise HTTPException(status_code=503, detail=exc.code) from exc


@router.get("/authorizations/official/callback")
def official_authorization_callback(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    state: str = Query(..., min_length=20, max_length=200),
    code: str | None = Query(None, min_length=1, max_length=400),
    error: str | None = Query(None, max_length=120),
) -> RedirectResponse:
    state_row = db.get(TikTokOAuthState, state_hash(state))
    return_to = state_row.return_to if state_row else "/enterprise/tiktok"
    if error or not code:
        if state_row:
            db.delete(state_row)
            db.commit()
        return RedirectResponse(
            _with_query(return_to, {"official_authorized": "0"}), status_code=302
        )
    try:
        authorizations = exchange_official_authorization(db, current_user, state=state, code=code)
    except TikTokOfficialError as exc:
        raise HTTPException(status_code=502, detail=exc.code) from exc
    return RedirectResponse(
        _with_query(
            return_to,
            {"official_authorized": "1", "authorization_count": str(len(authorizations))},
        ),
        status_code=302,
    )


@router.get("/mock/authorize")
def mock_authorize(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    state: str = Query(..., min_length=20, max_length=200),
) -> RedirectResponse:
    state_row = db.get(TikTokOAuthState, state_hash(state))
    if (
        not state_row
        or state_row.user_id != current_user.id
        or state_row.tenant_id != current_user.tenant_id
    ):
        raise HTTPException(status_code=400, detail="TikTok OAuth state is invalid or expired")
    code = approve_mock_authorization(db, state)
    parsed = urlsplit(state_row.return_to)
    query = urlencode(
        [
            *parse_qsl(parsed.query, keep_blank_values=True),
            ("tiktok_state", state),
            ("tiktok_code", code),
        ]
    )
    return RedirectResponse(
        urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment)),
        status_code=302,
    )


@router.get("/authorizations/callback")
def authorization_callback(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    state: str = Query(..., min_length=20, max_length=200),
    code: str = Query(..., min_length=20, max_length=200),
    code_verifier: str | None = Query(None, min_length=43, max_length=128),
) -> RedirectResponse:
    # The browser demo keeps the verifier in the client. API clients must pass it
    # explicitly; the mock authorize redirect cannot invent a verifier.
    if not code_verifier:
        raise HTTPException(status_code=400, detail="PKCE code_verifier is required")
    state_row = db.get(TikTokOAuthState, state_hash(state))
    if not state_row:
        raise HTTPException(status_code=400, detail="TikTok OAuth state is invalid or expired")
    if state_row.user_id != current_user.id or state_row.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403, detail="TikTok OAuth state does not belong to this user"
        )
    exchange_mock_authorization(db, state, code, code_verifier)
    return RedirectResponse(f"{state_row.return_to}?authorized=1", status_code=302)


def _with_query(path: str, values: dict[str, str]) -> str:
    parsed = urlsplit(path)
    query = urlencode([*parse_qsl(parsed.query, keep_blank_values=True), *values.items()])
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))


def _shadow_read(db: Session, row) -> TikTokShadowRunRead | None:
    if row is None:
        return None
    return TikTokShadowRunRead(
        id=row.id,
        status=row.status,
        started_at=row.started_at,
        ends_at=row.ends_at,
        last_heartbeat_at=row.last_heartbeat_at,
        observation_count=row.observation_count,
        error_count=row.error_count,
        baseline=dict(row.baseline_json or {}),
        quality=get_shadow_quality(db, row),
    )


@router.post("/authorizations/exchange", response_model=TikTokAuthorizationRead)
def authorization_exchange(
    request: TikTokAuthorizationExchange,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokAuthorizationRead:
    state_row = db.get(TikTokOAuthState, state_hash(request.state))
    if not state_row:
        raise HTTPException(status_code=400, detail="TikTok OAuth state is invalid or expired")
    if state_row.user_id != current_user.id or state_row.tenant_id != current_user.tenant_id:
        raise HTTPException(
            status_code=403, detail="TikTok OAuth state does not belong to this user"
        )
    authorization = exchange_mock_authorization(
        db, request.state, request.code, request.code_verifier
    )
    return TikTokAuthorizationRead(
        id=authorization.id,
        authorization_type=authorization.authorization_type,
        subject_id=authorization.subject_id,
        resource_id=authorization.resource_id,
        scopes=list(authorization.scopes_json or []),
        status=authorization.status,
        expires_at=authorization.expires_at,
    )


@router.get("/connector/read", response_model=TikTokConnectorRead)
def connector_read(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    authorization_type: str = Query(...),
    resource_id: str = Query(...),
    required_scope: str | None = Query(None),
) -> TikTokConnectorRead:
    return read_tiktok_resource(
        db,
        user=current_user,
        authorization_type=authorization_type,
        resource_id=resource_id,
        required_scope=required_scope,
    )
