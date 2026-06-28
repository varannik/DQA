"""Default tenant helpers for multi-tenancy migration."""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Tenant

DEFAULT_TENANT_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEFAULT_TENANT_SLUG = "default"


def get_or_create_default_tenant(db: Session) -> Tenant:
    tenant = db.query(Tenant).filter(Tenant.id == DEFAULT_TENANT_ID).first()
    if tenant:
        return tenant
    tenant = Tenant(
        id=DEFAULT_TENANT_ID,
        name="Default Tenant",
        slug=DEFAULT_TENANT_SLUG,
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def resolve_tenant_id(db: Session, tenant_id: Optional[uuid.UUID] = None) -> uuid.UUID:
    if tenant_id:
        return tenant_id
    return get_or_create_default_tenant(db).id
