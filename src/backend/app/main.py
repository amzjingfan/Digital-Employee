from __future__ import annotations

from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session

from app.a2a import recover_codex_a2a_tasks, stop_codex_a2a_tasks
from app.a2a import router as a2a_router
from app.accounts.casdoor_sync import start_casdoor_sync, stop_casdoor_sync
from app.api import (
    advertising,
    agents,
    app_updates,
    auth,
    authorization,
    bi,
    brands,
    business_executions,
    business_resources,
    channels,
    chat,
    crossborder_operations,
    crossborder_tools,
    designkit,
    evolution,
    feedback,
    general_skills,
    identity_roles,
    knowledge,
    knowledge_bases,
    memories,
    mock,
    model_configs,
    offsite_channels,
    oidc,
    operations_reports,
    persona,
    platform_tenants,
    product_lifecycle,
    scheduled_tasks,
    sessions,
    skills,
    social,
    teams,
    tiktok,
    tools,
    traces,
    ui_config,
    work_tasks,
)
from app.async_jobs import shutdown_async_jobs, start_async_jobs
from app.business_execution import start_execution_daemon, stop_execution_daemon
from app.channels import start_channel_services, stop_channel_services
from app.config import get_settings
from app.core.harness_recovery import (
    recover_orphan_harness_runs,
    start_harness_recovery_sweeper,
    stop_harness_recovery_sweeper,
)
from app.db import engine, init_db
from app.db.seed import seed_demo_data
from app.product_lifecycle.evidence_worker import (
    start_creative_evidence_worker,
    stop_creative_evidence_worker,
)
from app.public_api import create_public_api_app
from app.public_api.jobs import cleanup_public_api_records, recover_public_jobs
from app.public_api.maintenance import start_public_api_maintenance, stop_public_api_maintenance
from app.public_api.webhooks import enqueue_due_webhook_deliveries
from app.runtime_lock import acquire_runtime_instance_lock, release_runtime_instance_lock
from app.scheduled_tasks.worker import start_background_worker, stop_background_worker
from app.security.authorization import require_enterprise_permission
from app.security.runtime_config import validate_runtime_config
from app.teams.sweeper import start_timeout_sweeper, stop_timeout_sweeper
from app.tiktok.shadow_worker import start_shadow_worker, stop_shadow_worker
from app.tools.a2a_recovery import recover_a2a_client_tasks
from app.version import app_version
from app.work_tasks import start_work_task_daemon, stop_work_task_daemon

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=app_version(),
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def attach_request_id(request: Request, call_next):
    request_id = f"req_{uuid4().hex}"
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.on_event("startup")
def on_startup() -> None:
    acquire_runtime_instance_lock()
    try:
        validate_runtime_config(settings)
        init_db()
        if settings.database_seed_demo_data:
            with Session(engine) as db:
                seed_demo_data(db)
        if settings.staffdeck_role in {"all", "worker"}:
            start_async_jobs()
            with Session(engine) as db:
                recover_orphan_harness_runs(db, startup=True)
            recover_codex_a2a_tasks()
            recover_a2a_client_tasks()
            start_background_worker()
            start_creative_evidence_worker()
            start_casdoor_sync()
            start_shadow_worker()
            start_channel_services()
            start_timeout_sweeper()
            start_harness_recovery_sweeper()
            # Internal durable jobs (for example feedback analysis) use the same
            # recovery table even when the externally exposed API is disabled.
            recover_public_jobs()
            if settings.public_api_enabled:
                cleanup_public_api_records()
                enqueue_due_webhook_deliveries()
                start_public_api_maintenance()
        # The execution daemon uses tenant-scoped sessions and PostgreSQL leases,
        # so it remains safe in the API-only local deployment and across replicas.
        start_execution_daemon()
        start_work_task_daemon()
    except Exception:
        release_runtime_instance_lock()
        raise


@app.on_event("shutdown")
def on_shutdown() -> None:
    try:
        stop_execution_daemon()
        stop_work_task_daemon()
        if settings.staffdeck_role in {"all", "worker"}:
            stop_codex_a2a_tasks()
            stop_public_api_maintenance()
            stop_channel_services()
            stop_background_worker()
            stop_creative_evidence_worker()
            stop_casdoor_sync()
            stop_shadow_worker()
            stop_timeout_sweeper()
            stop_harness_recovery_sweeper()
            shutdown_async_jobs()
    finally:
        release_runtime_instance_lock()


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "app": "九骥 Joukir"}


app.include_router(app_updates.router)
app.include_router(chat.router)
app.include_router(agents.chat_router)
app.include_router(ui_config.chat_router)
app.include_router(auth.router)
app.include_router(oidc.router)
app.include_router(platform_tenants.router)
enterprise_permissions = [Depends(require_enterprise_permission)]
app.include_router(agents.scope_router, dependencies=enterprise_permissions)
app.include_router(advertising.router, dependencies=enterprise_permissions)
app.include_router(agents.enterprise_router, dependencies=enterprise_permissions)
app.include_router(general_skills.router, dependencies=enterprise_permissions)
app.include_router(knowledge_bases.router, dependencies=enterprise_permissions)
app.include_router(knowledge.router, dependencies=enterprise_permissions)
app.include_router(skills.router, dependencies=enterprise_permissions)
app.include_router(model_configs.router, dependencies=enterprise_permissions)
app.include_router(memories.router, dependencies=enterprise_permissions)
app.include_router(evolution.router, dependencies=enterprise_permissions)
app.include_router(feedback.router, dependencies=enterprise_permissions)
app.include_router(persona.router, dependencies=enterprise_permissions)
app.include_router(scheduled_tasks.enterprise_router, dependencies=enterprise_permissions)
app.include_router(scheduled_tasks.chat_router)
app.include_router(scheduled_tasks.chat_draft_router)
app.include_router(ui_config.enterprise_router, dependencies=enterprise_permissions)
app.include_router(channels.router, dependencies=enterprise_permissions)
app.include_router(teams.router, dependencies=enterprise_permissions)
app.include_router(teams.threads_router, dependencies=enterprise_permissions)
app.include_router(tools.router, dependencies=enterprise_permissions)
app.include_router(tools.mcp_router, dependencies=enterprise_permissions)
app.include_router(sessions.router, dependencies=enterprise_permissions)
app.include_router(traces.router, dependencies=enterprise_permissions)
app.include_router(authorization.router, dependencies=enterprise_permissions)
app.include_router(authorization.policy_router, dependencies=enterprise_permissions)
app.include_router(identity_roles.router, dependencies=enterprise_permissions)
app.include_router(brands.router, dependencies=enterprise_permissions)
app.include_router(business_resources.resource_router, dependencies=enterprise_permissions)
app.include_router(business_resources.request_router, dependencies=enterprise_permissions)
app.include_router(business_resources.approval_router, dependencies=enterprise_permissions)
app.include_router(social.router, dependencies=enterprise_permissions)
app.include_router(tiktok.router, dependencies=enterprise_permissions)
app.include_router(business_executions.router, dependencies=enterprise_permissions)
app.include_router(bi.router, dependencies=enterprise_permissions)
app.include_router(operations_reports.router, dependencies=enterprise_permissions)
app.include_router(crossborder_operations.router, dependencies=enterprise_permissions)
app.include_router(offsite_channels.router, dependencies=enterprise_permissions)
app.include_router(product_lifecycle.router, dependencies=enterprise_permissions)
app.include_router(work_tasks.router, dependencies=enterprise_permissions)
app.include_router(crossborder_tools.router)
app.include_router(designkit.router, dependencies=enterprise_permissions)
if settings.mock_api_enabled:
    app.include_router(mock.router)
app.include_router(a2a_router)

if settings.public_api_enabled:
    app.mount("/api/v1", create_public_api_app())
