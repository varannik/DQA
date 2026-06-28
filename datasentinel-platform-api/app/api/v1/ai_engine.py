from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import AITrainingFeedback, AuditLog

router = APIRouter()

@router.get("/feedback/stats")
def feedback_stats(project_id: Optional[UUID] = None,
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(AITrainingFeedback)
    if project_id: q = q.filter(AITrainingFeedback.project_id == project_id)
    all_feedback = q.all()
    by_field = {}
    by_error = {}
    for f in all_feedback:
        by_field[f.field_name] = by_field.get(f.field_name, 0) + 1
        by_error[f.error_type] = by_error.get(f.error_type, 0) + 1
    return {
        "total_feedback_records": len(all_feedback),
        "by_field": by_field,
        "by_error_type": by_error,
        "ready_for_training": {k: v for k, v in by_field.items() if v >= 50}
    }

@router.get("/models")
def list_models(db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(AITrainingFeedback).filter(AITrainingFeedback.used_in_training == True)
    trained = q.all()
    return {
        "models": [],
        "note": "Models trained in-memory per session. Persist via MLflow for production.",
        "total_training_records": len(trained)
    }
