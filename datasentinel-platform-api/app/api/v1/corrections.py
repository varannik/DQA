from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.models import (DQAViolation, CorrectionSuggestion, ApprovedCorrection,
                         AuditLog, AITrainingFeedback, Dataset, CorrectionRule, DQARun)
from app.schemas import SuggestionOut, ApprovalAction, BulkApproval, CorrectionRuleCreate
from app.engines.correction.engine import RuleBasedCorrectionEngine
from app.core.tenancy import resolve_tenant_id
from app.services.storage import get_dataset_store

from app.services.job_dispatcher import publish_correction_run, publish_ai_training
from sqlalchemy import func

router = APIRouter()

# ── Correction Rules ──────────────────────────────────────────────────────────
@router.get("/rules")
def list_correction_rules(project_id: Optional[UUID] = None,
                           db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(CorrectionRule)
    if project_id: q = q.filter(CorrectionRule.project_id == project_id)
    return [{"id": str(r.id), "name": r.name, "target_dqa_rule_id": r.target_dqa_rule_id,
              "correction_type": r.correction_type, "priority": r.priority,
              "is_active": r.is_active, "created_at": r.created_at.isoformat()} for r in q.all()]

@router.post("/rules")
def create_correction_rule(project_id: UUID, data: CorrectionRuleCreate,
                            db: Session = Depends(get_db), user=Depends(get_current_user)):
    tenant_id = resolve_tenant_id(db)
    rule = CorrectionRule(
        **data.model_dump(), project_id=project_id, tenant_id=tenant_id, created_by=user.id
    )
    db.add(rule); db.commit(); db.refresh(rule)
    return {"id": str(rule.id), "message": "Correction rule created"}

@router.patch("/rules/{rule_id}")
def update_correction_rule(rule_id: UUID, is_active: Optional[bool] = None,
                            priority: Optional[int] = None,
                            db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.query(CorrectionRule).filter(CorrectionRule.id == rule_id).first()
    if not r: raise HTTPException(404, "Rule not found")
    if is_active is not None: r.is_active = is_active
    if priority is not None: r.priority = priority
    db.commit()
    return {"message": "Updated"}

# ── Generate Suggestions ──────────────────────────────────────────────────────
@router.post("/generate/{run_id}")
def generate_suggestions(run_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    run = db.query(DQARun).filter(DQARun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    dataset = db.query(Dataset).filter(Dataset.id == run.dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    if settings.CORRECTION_EXECUTION_MODE == "sqs":
        job_id = publish_correction_run(db, run, dataset, user)
        return {"message": "Correction job queued", "job_id": job_id, "count": 0}

    violations = db.query(DQAViolation).filter(DQAViolation.run_id == run_id).all()
    correction_rules = db.query(CorrectionRule).filter(
        CorrectionRule.project_id == run.project_id, CorrectionRule.is_active == True
    ).all()
    dataset = db.query(Dataset).filter(Dataset.id == run.dataset_id).first()
    store = get_dataset_store()
    df = store.load_df(store.resolve_uri(dataset))
    crules_dicts = [{"id": str(r.id), "name": r.name, "target_dqa_rule_id": r.target_dqa_rule_id,
                      "correction_type": r.correction_type, "correction_logic": r.correction_logic,
                      "priority": r.priority, "is_active": r.is_active} for r in correction_rules]
    viols_dicts = [{"id": str(v.id), "rule_id": v.rule_id, "dimension": v.dimension,
                    "severity": v.severity, "affected_field": v.affected_field,
                    "affected_rows": v.affected_rows, "violation_detail": v.violation_detail} for v in violations]
    engine = RuleBasedCorrectionEngine()
    suggestions = engine.generate(df, viols_dicts, crules_dicts)
    created = 0
    for s in suggestions:
        violation = db.query(DQAViolation).filter(DQAViolation.id == s.violation_id).first()
        if not violation: continue
        existing = db.query(CorrectionSuggestion).filter(
            CorrectionSuggestion.violation_id == violation.id,
            CorrectionSuggestion.suggestion_source == s.suggestion_source
        ).first()
        if existing: continue
        sug = CorrectionSuggestion(
            tenant_id=run.tenant_id,
            violation_id=violation.id, dataset_id=run.dataset_id,
            suggestion_source=s.suggestion_source,
            original_value=s.original_value, suggested_value=s.suggested_value,
            correction_method=s.correction_method, confidence_score=s.confidence_score,
            explanation=s.explanation, feature_importance=s.feature_importance,
            status="pending"
        )
        db.add(sug); created += 1
    db.commit()
    return {"message": f"Generated {created} suggestions", "count": created}

# ── List Suggestions ──────────────────────────────────────────────────────────
@router.get("/suggestions", response_model=List[SuggestionOut])
def list_suggestions(violation_id: Optional[UUID] = None, dataset_id: Optional[UUID] = None,
                      status: Optional[str] = None,
                      db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(CorrectionSuggestion)
    if violation_id: q = q.filter(CorrectionSuggestion.violation_id == violation_id)
    if dataset_id: q = q.filter(CorrectionSuggestion.dataset_id == dataset_id)
    if status: q = q.filter(CorrectionSuggestion.status == status)
    return q.order_by(CorrectionSuggestion.created_at.desc()).limit(200).all()

@router.get("/suggestions/{suggestion_id}", response_model=SuggestionOut)
def get_suggestion(suggestion_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = db.query(CorrectionSuggestion).filter(CorrectionSuggestion.id == suggestion_id).first()
    if not s: raise HTTPException(404, "Suggestion not found")
    return s

# ── Approve / Reject / Override ───────────────────────────────────────────────
def _approve_suggestion(suggestion_id: UUID, db: Session, user,
                         override_value=None, override_reason=None):
    s = db.query(CorrectionSuggestion).filter(CorrectionSuggestion.id == suggestion_id).first()
    if not s: raise HTTPException(404, "Suggestion not found")
    if s.status != "pending":
        return  # already processed - silently skip (safe for bulk operations)
    s.status = "approved"; s.reviewed_by = user.id; s.reviewed_at = datetime.utcnow()
    if override_value is not None:
        s.override_value = override_value; s.override_reason = override_reason
    final_value = override_value if override_value is not None else s.suggested_value
    violation = db.query(DQAViolation).filter(DQAViolation.id == s.violation_id).first()
    approved = ApprovedCorrection(
        tenant_id=s.tenant_id,
        suggestion_id=s.id, dataset_id=s.dataset_id,
        field_name=violation.affected_field if violation else None,
        affected_rows=violation.affected_rows if violation else [],
        original_value=s.original_value, corrected_value=final_value,
        approved_by=user.id
    )
    db.add(approved)
    # AI training feedback
    feedback = AITrainingFeedback(
        tenant_id=s.tenant_id,
        correction_id=approved.id, dataset_id=s.dataset_id,
        field_name=violation.affected_field if violation else None,
        error_type=violation.rule_id if violation else None,
        feature_vector=s.feature_importance,
        target_value=final_value,
    )
    db.add(feedback)
    db.flush()
    if violation and violation.affected_field and violation.rule_id:
        run_obj = (
            db.query(DQARun)
            .join(DQAViolation, DQAViolation.run_id == DQARun.id)
            .filter(DQAViolation.id == s.violation_id)
            .first()
        )
        if run_obj:
            feedback.project_id = run_obj.project_id
            count = (
                db.query(func.count(AITrainingFeedback.id))
                .filter(
                    AITrainingFeedback.project_id == run_obj.project_id,
                    AITrainingFeedback.field_name == violation.affected_field,
                    AITrainingFeedback.error_type == violation.rule_id,
                )
                .scalar()
            )
            if count >= 50:
                publish_ai_training(
                    db,
                    run_obj.project_id,
                    s.tenant_id,
                    violation.affected_field,
                    violation.rule_id,
                    count,
                )
    db.add(AuditLog(
        event_type="correction_approved", entity_type="suggestion", entity_id=s.id,
        actor_id=user.id, actor_role=user.role,
        after_state={"corrected_value": final_value, "method": s.correction_method}
    ))
    if violation: violation.status = "in_review"
    db.commit()

@router.post("/approve")
def approve_suggestion(data: ApprovalAction, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _approve_suggestion(data.suggestion_id, db, user, data.override_value, data.override_reason)
    return {"message": "Suggestion approved"}

@router.post("/reject/{suggestion_id}")
def reject_suggestion(suggestion_id: UUID, reason: Optional[str] = None,
                       db: Session = Depends(get_db), user=Depends(get_current_user)):
    s = db.query(CorrectionSuggestion).filter(CorrectionSuggestion.id == suggestion_id).first()
    if not s: raise HTTPException(404, "Suggestion not found")
    s.status = "rejected"; s.reviewed_by = user.id; s.reviewed_at = datetime.utcnow()
    s.override_reason = reason
    db.add(AuditLog(event_type="correction_rejected", entity_type="suggestion", entity_id=s.id,
                     actor_id=user.id, actor_role=user.role, event_metadata={"reason": reason}))
    db.commit()
    return {"message": "Suggestion rejected"}

@router.post("/bulk-approve")
def bulk_approve(data: BulkApproval, db: Session = Depends(get_db), user=Depends(get_current_user)):
    approved_count = 0
    skip_count = 0
    for sid in data.suggestion_ids:
        try:
            s = db.query(CorrectionSuggestion).filter(CorrectionSuggestion.id == sid).first()
            if not s: skip_count += 1; continue
            if s.status != "pending": skip_count += 1; continue
            _approve_suggestion(sid, db, user)
            approved_count += 1
        except Exception:
            skip_count += 1
    return {"message": f"Approved {approved_count} suggestions ({skip_count} skipped)", "count": approved_count}

# ── Approved Corrections ──────────────────────────────────────────────────────
@router.get("/approved")
def list_approved(dataset_id: Optional[UUID] = None,
                   db: Session = Depends(get_db), user=Depends(get_current_user)):
    q = db.query(ApprovedCorrection)
    if dataset_id: q = q.filter(ApprovedCorrection.dataset_id == dataset_id)
    results = q.order_by(ApprovedCorrection.approved_at.desc()).limit(200).all()
    return [{"id": str(r.id), "field_name": r.field_name,
              "original_value": r.original_value, "corrected_value": r.corrected_value,
              "approved_at": r.approved_at.isoformat(),
              "applied_to_production": r.applied_to_production} for r in results]

@router.post("/apply/{dataset_id}")
def apply_corrections(dataset_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset: raise HTTPException(404, "Dataset not found")
    approved = db.query(ApprovedCorrection).filter(
        ApprovedCorrection.dataset_id == dataset_id,
        ApprovedCorrection.applied_to_production == False
    ).all()
    if not approved: return {"message": "No pending corrections to apply", "applied": 0}
    # Mark as applied
    for a in approved:
        a.applied_to_production = True; a.applied_at = datetime.utcnow()
    db.add(AuditLog(
        event_type="correction_applied", entity_type="dataset", entity_id=dataset_id,
        actor_id=user.id, actor_role=user.role,
        after_state={"corrections_applied": len(approved)}
    ))
    db.commit()
    return {"message": f"Marked {len(approved)} corrections as applied", "applied": len(approved)}

@router.get("/export/{dataset_id}")
def export_corrected_dataset(dataset_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset: raise HTTPException(404, "Dataset not found")
    store = get_dataset_store()
    df = store.load_df(store.resolve_uri(dataset))
    approved = db.query(ApprovedCorrection).filter(
        ApprovedCorrection.dataset_id == dataset_id,
        ApprovedCorrection.applied_to_production == True
    ).all()
    corrections_applied = 0
    for a in approved:
        field = a.field_name
        rows = a.affected_rows or []
        value = a.corrected_value
        if field and field in df.columns and rows and value is not None:
            df.loc[rows, field] = value
            corrections_applied += 1
    output = df.to_csv(index=False)
    return {
        "message": f"Dataset exported with {corrections_applied} corrections applied",
        "row_count": len(df),
        "corrections_applied": corrections_applied,
        "csv_preview": output[:2000]
    }
