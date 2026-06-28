from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AuditLog

router = APIRouter()

@router.get("/")
def list_audit(event_type: Optional[str] = None, entity_id: Optional[UUID] = None,
               limit: int = 100, db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(AuditLog)
    if event_type: q = q.filter(AuditLog.event_type == event_type)
    if entity_id: q = q.filter(AuditLog.entity_id == entity_id)
    results = q.order_by(AuditLog.created_at.desc()).limit(limit).all()
    return [
        {"id": str(r.id), "event_type": r.event_type, "entity_type": r.entity_type,
         "entity_id": str(r.entity_id) if r.entity_id else None,
         "actor_id": str(r.actor_id) if r.actor_id else None,
         "actor_role": r.actor_role, "event_metadata": r.event_metadata,
         "after_state": r.after_state,
         "created_at": r.created_at.isoformat()} for r in results
    ]
