from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.exc import DatabaseError
from sqlmodel import Session, select

from app.db import engine
from app.db.models import BusinessActionExecution, BusinessActionExecutionEvent


def _session(tenant_id: str) -> Session:
    db = Session(engine)
    db.info["staffdeck_tenant_id"] = tenant_id
    return db


def main() -> None:
    with _session("tenant_demo") as db:
        executions = db.exec(select(BusinessActionExecution)).all()
        events = db.exec(select(BusinessActionExecutionEvent)).all()
        if not executions or not events:
            raise RuntimeError("Expected the sandbox execution and its events")
        latest = max(executions, key=lambda row: row.created_at)
        if latest.status != "compensated":
            raise RuntimeError(f"Expected compensated demo execution, got {latest.status}")
        if latest.compensation_attempt_count != 1:
            raise RuntimeError("Expected exactly one compensation attempt")
        event_id = events[0].id
        try:
            db.execute(
                text(
                    "UPDATE business_action_execution_events "
                    "SET event_type = 'tampered' WHERE id = :event_id"
                ),
                {"event_id": event_id},
            )
            db.commit()
        except DatabaseError:
            db.rollback()
        else:
            raise RuntimeError("Append-only trigger allowed an event update")

    with _session("tenant_other") as db:
        if db.exec(select(BusinessActionExecution)).all():
            raise RuntimeError("Cross-tenant RLS exposed execution records")

    print(
        "Business execution runtime verification passed: sandbox execute/compensate, "
        "tenant RLS, and append-only events."
    )


if __name__ == "__main__":
    main()
