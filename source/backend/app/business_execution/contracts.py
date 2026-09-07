from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ExecutionDisposition = Literal[
    "succeeded",
    "retryable_failure",
    "terminal_failure",
    "unknown",
]


@dataclass(frozen=True)
class ExecutionContext:
    execution_id: str
    tenant_id: str
    request_id: str
    resource_id: str
    resource_type: str
    resource_code: str
    action_type: str
    payload: dict[str, Any]
    resource_metadata: dict[str, Any]
    connector_type: str
    environment: str
    idempotency_key: str
    attempt_no: int


@dataclass(frozen=True)
class ConnectorOutcome:
    disposition: ExecutionDisposition
    external_operation_id: str | None = None
    receipt: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    retry_after_seconds: float | None = None


class BusinessConnector:
    connector_type = "base"
    replay_safe = False

    def execute(self, context: ExecutionContext) -> ConnectorOutcome:
        raise NotImplementedError

    def compensate(self, context: ExecutionContext, receipt: dict[str, Any]) -> ConnectorOutcome:
        return ConnectorOutcome(
            disposition="terminal_failure",
            error_code="compensation_not_supported",
            error_message=f"{self.connector_type} does not support compensation for this action",
        )
