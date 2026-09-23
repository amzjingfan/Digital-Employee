from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AgentResourceType = Literal["skill", "general_skill", "knowledge_base", "tool"]
AgentWorkRecordEventKind = Literal["chat", "task", "sop", "tool", "knowledge", "skill"]
AgentWorkRecordEventPhase = Literal["reply", "last_run", "next_run", "assigned"]


class AgentProfileCreateRequest(BaseModel):
    tenant_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    persona_prompt: Optional[str] = None
    is_overall: bool = False
    source_mode: Literal["copy", "blank"] = "copy"
    copy_from_agent_id: Optional[str] = None
    harness_max_actions: int = Field(default=32, ge=1, le=100)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentDescriptionGenerateRequest(BaseModel):
    tenant_id: str
    role_name: str = Field(max_length=80)

    model_config = ConfigDict(extra="forbid")


class AgentDescriptionGenerateResponse(BaseModel):
    description: str


class AgentProfileUpdateRequest(BaseModel):
    tenant_id: str
    name: Optional[str] = None
    description: Optional[str] = None
    persona_prompt: Optional[str] = None
    status: Optional[Literal["active", "archived"]] = None
    harness_max_actions: Optional[int] = Field(default=None, ge=1, le=100)
    metadata: Optional[dict[str, Any]] = None


class AgentResourceBindingRead(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    resource_type: AgentResourceType
    resource_id: str
    status: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class AgentProfileRead(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    persona_prompt: Optional[str] = None
    is_overall: bool
    status: str
    release_state: Literal["draft", "published"] = "draft"
    published_release_id: Optional[str] = None
    published_release_version: int = 0
    harness_max_actions: int = 32
    metadata: dict[str, Any] = Field(default_factory=dict)
    resources: list[AgentResourceBindingRead] = Field(default_factory=list)
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class AgentScopeRead(BaseModel):
    tenant_id: str
    agents: list[AgentProfileRead] = Field(default_factory=list)


class AgentWorkRecordReplyStatsRead(BaseModel):
    total: int = 0
    today: int = 0
    by_day: dict[str, int] = Field(default_factory=dict)


class AgentWorkRecordEventRead(BaseModel):
    id: str
    kind: AgentWorkRecordEventKind
    phase: AgentWorkRecordEventPhase
    timestamp: str
    label: str = ""


class AgentWorkRecordRead(BaseModel):
    agent_id: str
    timezone: str
    generated_at: str
    reply_stats: AgentWorkRecordReplyStatsRead
    events: list[AgentWorkRecordEventRead] = Field(default_factory=list)


class AgentResourceBindingInput(BaseModel):
    resource_type: AgentResourceType
    resource_id: str
    status: Literal["active", "inactive"] = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentResourcesUpdateRequest(BaseModel):
    tenant_id: str
    resources: list[AgentResourceBindingInput] = Field(default_factory=list)


class AgentResourceImportRequest(BaseModel):
    tenant_id: str
    source_agent_id: str
    resource_type: AgentResourceType
    resource_ids: list[str] = Field(default_factory=list)


class AgentModelBindingInput(BaseModel):
    role: Literal["default", "router", "step", "response", "general_skill"]
    model_config_id: str


class AgentModelsUpdateRequest(BaseModel):
    tenant_id: str
    bindings: list[AgentModelBindingInput] = Field(default_factory=list)


class AgentModelBindingRead(BaseModel):
    role: str
    model_config_id: str
    effective: bool = False


class AgentSkillRollbackRequest(BaseModel):
    tenant_id: str
    version: str


class AgentReleasePublishRequest(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=3, max_length=1000)


class AgentReleaseRollbackRequest(BaseModel):
    tenant_id: str
    reason: str = Field(min_length=3, max_length=1000)


class AgentReleaseRead(BaseModel):
    id: str
    tenant_id: str
    agent_id: str
    version: int
    status: Literal["published", "superseded"]
    snapshot: dict[str, Any] = Field(default_factory=dict)
    snapshot_digest: str
    source_release_id: Optional[str] = None
    created_by_user_id: str
    release_reason: str
    created_at: datetime
    published_at: datetime


class AgentReleaseDiffRead(BaseModel):
    agent_id: str
    left_release_id: str
    right_release_id: str
    changes: list[dict[str, Any]] = Field(default_factory=list)


class AgentReleaseEventRead(BaseModel):
    id: str
    agent_id: str
    release_id: Optional[str] = None
    event_type: Literal["published", "rolled_back", "draft_changed", "deactivated"]
    actor_user_id: str
    detail: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime


class AgentAPICredentialCreateRequest(BaseModel):
    tenant_id: str
    name: str = Field(min_length=1, max_length=120)
    access: Literal["runtime"] = "runtime"
    expires_at: datetime | None = None


class AgentAPICredentialRead(BaseModel):
    id: str
    agent_id: str
    name: str
    access: Literal["runtime", "full_access"]
    key_prefix: str
    scopes: list[str] = Field(default_factory=list)
    status: str
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None


class AgentAPICredentialCreated(AgentAPICredentialRead):
    api_key: str
