from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import DQAViolation, CorrectionSuggestion, ApprovedCorrection, AuditLog, AITrainingFeedback, Dataset, CorrectionRule
from app.schemas import ViolationOut, SuggestionOut, ApprovalAction, BulkApproval, CorrectionRuleCreate
from app.engines.correction.engine import RuleBasedCorrectionEngine
import os, pandas as pd

router = APIRouter()

@router.get("/", response_model=List[ViolationOut])
def list_violations(run_id: Optional[UUID] = None, dataset_id: Optional[UUID] = None,
                    severity: Optional[str] = None, status: Optional[str] = None,
                    dimension: Optional[str] = None,
                    db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(DQAViolation)
    if run_id: q = q.filter(DQAViolation.run_id == run_id)
    if dataset_id: q = q.filter(DQAViolation.dataset_id == dataset_id)
    if severity: q = q.filter(DQAViolation.severity == severity)
    if status: q = q.filter(DQAViolation.status == status)
    if dimension: q = q.filter(DQAViolation.dimension == dimension)
    return q.order_by(DQAViolation.created_at.desc()).limit(500).all()

@router.get("/{violation_id}", response_model=ViolationOut)
def get_violation(violation_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    v = db.query(DQAViolation).filter(DQAViolation.id == violation_id).first()
    if not v: raise HTTPException(404, "Violation not found")
    return v

@router.patch("/{violation_id}/status")
def update_violation_status(violation_id: UUID, status: str,
                             db: Session = Depends(get_db), user=Depends(get_current_user)):
    v = db.query(DQAViolation).filter(DQAViolation.id == violation_id).first()
    if not v: raise HTTPException(404, "Violation not found")
    v.status = status; db.commit()
    return {"message": "Status updated", "status": status}
