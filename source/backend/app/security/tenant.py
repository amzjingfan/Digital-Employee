from fastapi import HTTPException
from sqlmodel import Session

from app.db.models import Tenant


def ensure_tenant(session: Session, tenant_id: str) -> Tenant:
    tenant = session.get(Tenant, tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {tenant_id}")
    if tenant.status != "active":
        raise HTTPException(status_code=403, detail="Tenant is not active")
    return tenant
