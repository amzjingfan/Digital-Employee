from __future__ import annotations

import argparse
import time
from collections.abc import Mapping, Sequence

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlmodel import Session, select

from app.db.database import engine, set_tenant_context
from app.db.models import User, WorkTask, WorkTaskExecutionSnapshot, WorkTaskRun
from app.work_tasks.schema import WorkTaskCreate
from app.work_tasks.service import create_task
from app.work_tasks.snapshots import execution_snapshot_digest


def contains_secret_material(value: object) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).lower()
            if normalized in {"client_secret", "access_token", "refresh_token", "id_token"}:
                return True
            if contains_secret_material(item):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(contains_secret_material(item) for item in value)
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify work-task execution snapshot and M2M trace")
    parser.add_argument("--tenant-id", default="tenant_demo")
    args = parser.parse_args()
    key = "verification:m2m-snapshot-v2:20260902"
    with Session(engine) as db:
        set_tenant_context(db, args.tenant_id)
        manager = db.exec(
            select(User).where(
                User.tenant_id == args.tenant_id,
                User.business_role.in_(["operations_supervisor", "platform_admin"]),
            )
        ).first()
        if manager is None:
            raise RuntimeError("No operations supervisor or platform administrator exists")
        task_read = create_task(
            db,
            request=WorkTaskCreate(
                tenant_id=args.tenant_id,
                idempotency_key=key,
                title="验证物流岗位启动快照与 M2M 身份",
                description="仅执行沙箱分析，不调用外部业务写操作。",
                owner_business_role="logistics_exception_specialist",
                priority="normal",
                risk_level="low",
            ),
            user=manager,
        )
        task_id = task_read.id

    deadline = time.monotonic() + 30
    task: WorkTask | None = None
    run: WorkTaskRun | None = None
    snapshot: WorkTaskExecutionSnapshot | None = None
    while time.monotonic() < deadline:
        with Session(engine) as db:
            set_tenant_context(db, args.tenant_id)
            task = db.exec(
                select(WorkTask).where(WorkTask.tenant_id == args.tenant_id, WorkTask.id == task_id)
            ).one()
            run = db.exec(
                select(WorkTaskRun)
                .where(WorkTaskRun.tenant_id == args.tenant_id, WorkTaskRun.task_id == task_id)
                .order_by(WorkTaskRun.attempt_no.desc())
            ).first()
            if run and run.execution_snapshot_id:
                snapshot = db.exec(
                    select(WorkTaskExecutionSnapshot).where(
                        WorkTaskExecutionSnapshot.tenant_id == args.tenant_id,
                        WorkTaskExecutionSnapshot.id == run.execution_snapshot_id,
                    )
                ).one()
            if task.status in {"review", "failed"}:
                break
        time.sleep(0.5)

    if task is None or run is None or snapshot is None:
        raise RuntimeError("Worker did not persist a complete execution context")
    if task.status != "review" or run.status != "succeeded":
        raise RuntimeError(f"Unexpected task/run state: {task.status}/{run.status}")
    if run.snapshot_digest != snapshot.snapshot_digest:
        raise RuntimeError("Run and snapshot digests differ")
    if execution_snapshot_digest(snapshot) != snapshot.snapshot_digest:
        raise RuntimeError("Execution snapshot digest does not match its canonical content")
    if run.service_identity_id != snapshot.service_identity_id:
        raise RuntimeError("Run and snapshot service identities differ")
    if contains_secret_material(
        {
            "agent": snapshot.agent_snapshot_json,
            "sops": snapshot.sop_snapshots_json,
            "knowledge": snapshot.knowledge_snapshots_json,
            "tools": snapshot.tool_snapshots_json,
            "capabilities": snapshot.capability_snapshot_json,
            "identity": snapshot.service_identity_snapshot_json,
            "trace": run.trace_json,
        }
    ):
        raise RuntimeError("Secret-shaped material was persisted in snapshot or Trace")
    service_trace = dict(run.trace_json or {}).get("service_identity")
    if not isinstance(service_trace, dict) or service_trace.get("status") != "verified":
        raise RuntimeError("Run Trace does not contain a verified service identity receipt")
    with Session(engine) as db:
        set_tenant_context(db, args.tenant_id)
        try:
            db.exec(
                text(
                    "UPDATE work_task_execution_snapshots "
                    "SET snapshot_digest = snapshot_digest WHERE id = :snapshot_id"
                ).bindparams(snapshot_id=snapshot.id)
            )
            db.commit()
        except DBAPIError:
            db.rollback()
        else:
            raise RuntimeError("Append-only database trigger did not reject snapshot mutation")
    print(
        f"verified task={task_id} status=review snapshot={snapshot.id} "
        f"sops={len(snapshot.sop_snapshots_json)} "
        f"knowledge={len(snapshot.knowledge_snapshots_json)} "
        f"tools={len(snapshot.tool_snapshots_json)} secrets_persisted=0 append_only=verified"
    )


if __name__ == "__main__":
    main()
