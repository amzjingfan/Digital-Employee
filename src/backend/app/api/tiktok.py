from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.agents.releases import AgentReleaseError
from app.db import get_session
from app.db.models import TikTokOAuthState, User
from app.security.auth import get_current_user
from app.tiktok.commission_drafts import (
    CommissionDraftConflict,
    CommissionDraftRead,
    CommissionDraftSaveRequest,
    list_commission_drafts,
    save_commission_draft,
)
from app.tiktok.commission_preflight import (
    CommissionPreflightRequest,
    CommissionPreflightResult,
    preflight_commission_draft,
)
from app.tiktok.connector import TikTokConnectorRead, read_tiktok_resource
from app.tiktok.creator_pool import (
    CreatorPoolConflict,
    PoolAssignmentRequest,
    PoolEntryRead,
    PoolFollowUpRequest,
    PoolIntakeRequest,
    PoolResponsibilitiesRequest,
    PoolRevisionRequest,
    PoolWorkspace,
    approve_reflow,
    assign_creator,
    claim_creator,
    enter_creator_pool,
    get_creator_pool,
    propose_reflow,
    record_effective_follow_up,
    set_creator_responsibilities,
)
from app.tiktok.data_validation import (
    TikTokDataValidationConflict,
    TikTokDataValidationNotFound,
    bootstrap_data_validation_workspace,
    get_data_validation_workspace,
    run_mock_data_validation,
    run_recorded_data_validation,
    update_capability_evidence,
    update_data_validation_scope,
    update_field_contract,
)
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
from app.tiktok.p3b1_history import (
    HistoryConfirmRequest,
    HistoryConflict,
    HistoryImportResult,
    HistorySignoffRead,
    HistoryWorkspace,
    ReconciliationRead,
    ReconciliationRequest,
    confirm_history_reconciliation,
    get_history_workspace,
    import_history,
    read_history_import_request,
    record_reconciliation,
)
from app.tiktok.recorded_validation import (
    TikTokRecordedValidationInputError,
    read_recorded_validation_request,
)
from app.tiktok.schema import (
    TikTokAgentReleasePreflight,
    TikTokAgentReleasePublishRequest,
    TikTokAgentReleasePublishResult,
    TikTokAssetBootstrapResponse,
    TikTokAuthorizationExchange,
    TikTokAuthorizationRead,
    TikTokBootstrapResponse,
    TikTokCapabilityEvidenceRead,
    TikTokCapabilityEvidenceUpdate,
    TikTokDataValidationBootstrapResponse,
    TikTokDataValidationRunRead,
    TikTokDataValidationScopeRead,
    TikTokDataValidationScopeUpdate,
    TikTokDataValidationWorkspace,
    TikTokFieldContractRead,
    TikTokFieldContractUpdate,
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
    revoke_tiktok_authorization,
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


def _creator_pool_action(db: Session, operation: Callable[[], PoolEntryRead]) -> PoolEntryRead:
    try:
        return operation()
    except CreatorPoolConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={
            "code": exc.code,
            "current_owner_user_id": exc.current_owner_user_id,
            "revision": exc.revision,
        }) from exc


@router.get("/creator-pool", response_model=PoolWorkspace)
def creator_pool_list(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolWorkspace:
    return get_creator_pool(db, current_user)


@router.post("/creator-pool", response_model=PoolEntryRead)
def creator_pool_intake(
    request: PoolIntakeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolEntryRead:
    return _creator_pool_action(db, lambda: enter_creator_pool(db, current_user, request))


@router.post("/creator-claims/{entry_id}", response_model=PoolEntryRead)
def creator_pool_claim(
    entry_id: str,
    request: PoolRevisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolEntryRead:
    return _creator_pool_action(db, lambda: claim_creator(
        db, current_user, entry_id, expected_revision=request.expected_revision,
    ))


@router.post("/creator-follow-ups/{entry_id}", response_model=PoolEntryRead)
def creator_pool_follow_up(
    entry_id: str,
    request: PoolFollowUpRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolEntryRead:
    return _creator_pool_action(db, lambda: record_effective_follow_up(
        db, current_user, entry_id, expected_revision=request.expected_revision,
        evidence_ref=request.evidence_ref,
    ))


@router.post("/creator-reflow-proposals/{entry_id}", response_model=PoolEntryRead)
def creator_pool_reflow_propose(
    entry_id: str,
    request: PoolRevisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolEntryRead:
    return _creator_pool_action(db, lambda: propose_reflow(
        db, current_user, entry_id, expected_revision=request.expected_revision,
    ))


@router.post("/creator-reflow-approvals/{entry_id}", response_model=PoolEntryRead)
def creator_pool_reflow_approve(
    entry_id: str,
    request: PoolRevisionRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolEntryRead:
    return _creator_pool_action(db, lambda: approve_reflow(
        db, current_user, entry_id, expected_revision=request.expected_revision,
    ))


@router.post("/creator-assignments/{entry_id}", response_model=PoolEntryRead)
def creator_pool_assign(
    entry_id: str,
    request: PoolAssignmentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolEntryRead:
    return _creator_pool_action(db, lambda: assign_creator(
        db, current_user, entry_id, expected_revision=request.expected_revision,
        target_user_id=request.target_user_id, reason=request.reason,
    ))


@router.post("/creator-responsibilities/{entry_id}", response_model=PoolEntryRead)
def creator_pool_responsibilities(
    entry_id: str,
    request: PoolResponsibilitiesRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> PoolEntryRead:
    return _creator_pool_action(db, lambda: set_creator_responsibilities(
        db, current_user, entry_id, expected_revision=request.expected_revision,
        fulfillment_user_id=request.fulfillment_user_id,
        maintenance_user_id=request.maintenance_user_id,
    ))


@router.post(
    "/commission-drafts/{entry_id}/preflight", response_model=CommissionPreflightResult,
)
def commission_draft_preflight(
    entry_id: str,
    request: CommissionPreflightRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> CommissionPreflightResult:
    return preflight_commission_draft(db, current_user, entry_id, request)


@router.get("/commission-drafts/{entry_id}", response_model=list[CommissionDraftRead])
def commission_drafts_list(
    entry_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> list[CommissionDraftRead]:
    return list_commission_drafts(db, current_user, entry_id)


@router.post("/commission-drafts/{entry_id}", response_model=CommissionDraftRead)
def commission_drafts_save(
    entry_id: str,
    request: CommissionDraftSaveRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> CommissionDraftRead:
    try:
        return save_commission_draft(db, current_user, entry_id, request)
    except CommissionDraftConflict as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": str(exc)}) from exc


@router.get("/history", response_model=HistoryWorkspace)
def history_workspace(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    domain: str | None = None,
    creator_id: str | None = None,
    product_id: str | None = None,
    assigned_bd_user_id: str | None = None,
    observed_from: datetime | None = None,
    observed_until: datetime | None = None,
    page: int = 1,
    limit: int = 100,
) -> HistoryWorkspace:
    return get_history_workspace(
        db, current_user, domain=domain, creator_id=creator_id, product_id=product_id,
        assigned_bd_user_id=assigned_bd_user_id, observed_from=observed_from,
        observed_until=observed_until, page=page, limit=limit,
    )


@router.post("/history/import", response_model=HistoryImportResult)
async def history_import(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> HistoryImportResult:
    from app.security.permissions import ensure_tenant_admin

    ensure_tenant_admin(current_user.tenant_id, current_user)
    try:
        payload = await read_history_import_request(request)
        return import_history(db, current_user, payload)
    except TikTokRecordedValidationInputError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.code},
        ) from exc
    except HistoryConflict as exc:
        db.rollback()
        raise _history_http_error(exc) from exc


@router.post("/history/facts/{fact_id}/reconciliations", response_model=ReconciliationRead)
def history_reconcile(
    fact_id: str,
    request: ReconciliationRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> ReconciliationRead:
    try:
        return record_reconciliation(db, current_user, fact_id, request)
    except HistoryConflict as exc:
        db.rollback()
        raise _history_http_error(exc) from exc


@router.post("/history/confirm", response_model=HistorySignoffRead)
def history_confirm(
    request: HistoryConfirmRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> HistorySignoffRead:
    try:
        return confirm_history_reconciliation(
            db, current_user, approval_ref=request.approval_ref,
            source_evidence_ref=request.source_evidence_ref,
            source_attested=request.source_attested,
        )
    except HistoryConflict as exc:
        db.rollback()
        raise _history_http_error(exc) from exc


def _history_http_error(exc: HistoryConflict) -> HTTPException:
    code = str(exc)
    return HTTPException(
        status_code=404 if code.endswith("_not_found") else 409,
        detail={"code": code, "message": code},
    )


@router.get("/data-validation", response_model=TikTokDataValidationWorkspace)
def data_validation_workspace(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokDataValidationWorkspace:
    return get_data_validation_workspace(db, current_user)


@router.post(
    "/data-validation/bootstrap",
    response_model=TikTokDataValidationBootstrapResponse,
)
def data_validation_bootstrap(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokDataValidationBootstrapResponse:
    return bootstrap_data_validation_workspace(db, current_user)


@router.put(
    "/data-validation/pilot-scope",
    response_model=TikTokDataValidationScopeRead,
)
def data_validation_scope_update(
    request: TikTokDataValidationScopeUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokDataValidationScopeRead:
    try:
        return update_data_validation_scope(db, current_user, request)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        db.rollback()
        raise _data_validation_http_error(exc) from exc


@router.put(
    "/data-validation/field-contracts/{field_code}",
    response_model=TikTokFieldContractRead,
)
def data_validation_field_update(
    field_code: str,
    request: TikTokFieldContractUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokFieldContractRead:
    try:
        return update_field_contract(db, current_user, field_code, request)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        db.rollback()
        raise _data_validation_http_error(exc) from exc


@router.put(
    "/data-validation/capability-evidence/{entry_code}",
    response_model=TikTokCapabilityEvidenceRead,
)
def data_validation_evidence_update(
    entry_code: str,
    request: TikTokCapabilityEvidenceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokCapabilityEvidenceRead:
    try:
        return update_capability_evidence(db, current_user, entry_code, request)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        db.rollback()
        raise _data_validation_http_error(exc) from exc


@router.post("/data-validation/runs/mock", response_model=TikTokDataValidationRunRead)
def data_validation_mock_run(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokDataValidationRunRead:
    try:
        return run_mock_data_validation(db, current_user)
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        db.rollback()
        raise _data_validation_http_error(exc) from exc


@router.post(
    "/data-validation/runs/recorded",
    response_model=TikTokDataValidationRunRead,
)
async def data_validation_recorded_run(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokDataValidationRunRead:
    try:
        payload = await read_recorded_validation_request(request)
        return run_recorded_data_validation(db, current_user, payload)
    except TikTokRecordedValidationInputError as exc:
        db.rollback()
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.code},
        ) from exc
    except (TikTokDataValidationNotFound, TikTokDataValidationConflict) as exc:
        db.rollback()
        raise _data_validation_http_error(exc) from exc


def _data_validation_http_error(
    exc: TikTokDataValidationNotFound | TikTokDataValidationConflict,
) -> HTTPException:
    code, _, message = str(exc).partition(":")
    status_code = 409 if isinstance(exc, TikTokDataValidationConflict) else 404
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message.strip() or code},
    )


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


@router.post(
    "/authorizations/{authorization_id}/revoke",
    response_model=TikTokAuthorizationRead,
)
def revoke_authorization(
    authorization_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> TikTokAuthorizationRead:
    return revoke_tiktok_authorization(db, current_user, authorization_id)
