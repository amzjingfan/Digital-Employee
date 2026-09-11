from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.crossborder.schema import (
    AfterSalesCaseCreate,
    AfterSalesCaseRead,
    AfterSalesClassification,
    AfterSalesClose,
    AfterSalesDraft,
    AfterSalesQueryResult,
    CrossborderOverview,
    HumanExceptionResolution,
    IntegrationHealthRead,
    IntegrationHealthReport,
    LogisticsAnomalyBatchCreate,
    LogisticsAnomalyBatchRead,
    LogisticsAnomalyRead,
    LogisticsEscalation,
    LogisticsResolution,
)
from app.crossborder.service import (
    classify_after_sales_case,
    close_after_sales_case,
    create_after_sales_case,
    crossborder_overview,
    draft_after_sales_resolution,
    escalate_logistics_anomaly,
    get_after_sales_case,
    get_logistics_anomaly,
    ingest_logistics_anomalies,
    list_after_sales_cases,
    list_integration_health,
    list_logistics_anomalies,
    record_after_sales_query,
    report_integration_health,
    resolve_after_sales_exception,
    resolve_logistics_anomaly,
)
from app.db import get_session
from app.db.models import User
from app.security.auth import get_current_user

router = APIRouter(
    prefix="/api/enterprise/work-tasks/crossborder",
    tags=["enterprise:crossborder-operations"],
)


@router.get("/overview", response_model=CrossborderOverview)
def get_overview(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> CrossborderOverview:
    return crossborder_overview(db, tenant_id=tenant_id, user=current_user)


@router.get("/after-sales", response_model=list[AfterSalesCaseRead])
def get_after_sales_cases(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    status: Annotated[str | None, Query()] = None,
) -> list[AfterSalesCaseRead]:
    return list_after_sales_cases(db, tenant_id=tenant_id, user=current_user, status=status)


@router.post("/after-sales", response_model=AfterSalesCaseRead)
def post_after_sales_case(
    request: AfterSalesCaseCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AfterSalesCaseRead:
    return create_after_sales_case(db, request=request, user=current_user)


@router.get("/after-sales/{case_id}", response_model=AfterSalesCaseRead)
def get_after_sales_case_detail(
    case_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> AfterSalesCaseRead:
    return get_after_sales_case(db, tenant_id=tenant_id, case_id=case_id, user=current_user)


@router.post("/after-sales/{case_id}/query", response_model=AfterSalesCaseRead)
def post_after_sales_query(
    case_id: str,
    request: AfterSalesQueryResult,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AfterSalesCaseRead:
    return record_after_sales_query(db, case_id=case_id, request=request, user=current_user)


@router.post("/after-sales/{case_id}/classify", response_model=AfterSalesCaseRead)
def post_after_sales_classification(
    case_id: str,
    request: AfterSalesClassification,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AfterSalesCaseRead:
    return classify_after_sales_case(db, case_id=case_id, request=request, user=current_user)


@router.post("/after-sales/{case_id}/draft", response_model=AfterSalesCaseRead)
def post_after_sales_draft(
    case_id: str,
    request: AfterSalesDraft,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AfterSalesCaseRead:
    return draft_after_sales_resolution(db, case_id=case_id, request=request, user=current_user)


@router.post("/after-sales/{case_id}/resolve-exception", response_model=AfterSalesCaseRead)
def post_after_sales_exception_resolution(
    case_id: str,
    request: HumanExceptionResolution,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AfterSalesCaseRead:
    return resolve_after_sales_exception(db, case_id=case_id, request=request, user=current_user)


@router.post("/after-sales/{case_id}/close", response_model=AfterSalesCaseRead)
def post_after_sales_close(
    case_id: str,
    request: AfterSalesClose,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> AfterSalesCaseRead:
    return close_after_sales_case(db, case_id=case_id, request=request, user=current_user)


@router.get("/logistics", response_model=list[LogisticsAnomalyRead])
def get_logistics_anomalies(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
    status: Annotated[str | None, Query()] = None,
    cluster_key: Annotated[str | None, Query()] = None,
) -> list[LogisticsAnomalyRead]:
    return list_logistics_anomalies(
        db,
        tenant_id=tenant_id,
        user=current_user,
        status=status,
        cluster_key=cluster_key,
    )


@router.post("/logistics/ingest", response_model=LogisticsAnomalyBatchRead)
def post_logistics_anomalies(
    request: LogisticsAnomalyBatchCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> LogisticsAnomalyBatchRead:
    return ingest_logistics_anomalies(db, request=request, user=current_user)


@router.get("/logistics/{anomaly_id}", response_model=LogisticsAnomalyRead)
def get_logistics_anomaly_detail(
    anomaly_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> LogisticsAnomalyRead:
    return get_logistics_anomaly(
        db, tenant_id=tenant_id, anomaly_id=anomaly_id, user=current_user
    )


@router.post("/logistics/{anomaly_id}/escalate", response_model=LogisticsAnomalyRead)
def post_logistics_escalation(
    anomaly_id: str,
    request: LogisticsEscalation,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> LogisticsAnomalyRead:
    return escalate_logistics_anomaly(
        db, anomaly_id=anomaly_id, request=request, user=current_user
    )


@router.post("/logistics/{anomaly_id}/resolve", response_model=LogisticsAnomalyRead)
def post_logistics_resolution(
    anomaly_id: str,
    request: LogisticsResolution,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> LogisticsAnomalyRead:
    return resolve_logistics_anomaly(
        db, anomaly_id=anomaly_id, request=request, user=current_user
    )


@router.get("/integration-health", response_model=list[IntegrationHealthRead])
def get_integration_health(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
    tenant_id: Annotated[str, Query()],
) -> list[IntegrationHealthRead]:
    return list_integration_health(db, tenant_id=tenant_id, user=current_user)


@router.post("/integration-health/report", response_model=IntegrationHealthRead)
def post_integration_health(
    request: IntegrationHealthReport,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_session)],
) -> IntegrationHealthRead:
    return report_integration_health(db, request=request, user=current_user)
