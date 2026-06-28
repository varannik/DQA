from fastapi import APIRouter, Depends
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
import secrets

from app.core.database import get_db
from app.core.security import get_current_user, require_scope
from app.core.tenancy import resolve_tenant_id
from app.models import Webhook

router = APIRouter()


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = ["dqa.run.completed"]


@router.post("/")
def register_webhook(
    data: WebhookCreate,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _=Depends(require_scope("webhooks:write")),
):
    tenant_id = resolve_tenant_id(db)
    secret = secrets.token_urlsafe(32)
    hook = Webhook(
        tenant_id=tenant_id,
        url=str(data.url),
        events=data.events,
        secret=secret,
    )
    db.add(hook)
    db.commit()
    db.refresh(hook)
    return {"id": str(hook.id), "secret": secret, "url": hook.url, "events": hook.events}


@router.get("/")
def list_webhooks(db: Session = Depends(get_db), user=Depends(get_current_user)):
    tenant_id = resolve_tenant_id(db)
    hooks = db.query(Webhook).filter(Webhook.tenant_id == tenant_id).all()
    return [
        {"id": str(h.id), "url": h.url, "events": h.events, "is_active": h.is_active}
        for h in hooks
    ]
