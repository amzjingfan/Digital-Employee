from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

BrandStatus = Literal["active", "inactive", "archived"]
BrandAccessLevel = Literal["viewer", "operator"]
AssignmentStatus = Literal["active", "inactive"]


class BrandCreate(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=160)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)


class BrandRead(BaseModel):
    id: str
    tenant_id: str
    code: str
    name: str
    timezone: str
    status: BrandStatus
    revision: int
    access_level: BrandAccessLevel
    created_at: datetime
    updated_at: datetime


class BrandMembershipPut(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    access_level: BrandAccessLevel = "viewer"
    status: AssignmentStatus = "active"


class BrandMembershipRead(BaseModel):
    id: str
    tenant_id: str
    brand_id: str
    user_id: str
    access_level: BrandAccessLevel
    status: AssignmentStatus
    created_by_user_id: str
    created_at: datetime
    updated_at: datetime


class StoreAccessPut(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    status: AssignmentStatus = "active"


class BrandStoreRead(BaseModel):
    access_id: str
    tenant_id: str
    brand_id: str
    resource_id: str
    code: str
    name: str
    status: AssignmentStatus
    created_at: datetime
    updated_at: datetime


class BrandAccessEventRead(BaseModel):
    id: str
    tenant_id: str
    brand_id: str
    event_type: Literal["brand_created", "membership_changed", "store_access_changed"]
    actor_user_id: str
    subject_user_id: str | None
    resource_id: str | None
    detail: dict[str, object]
    occurred_at: datetime
