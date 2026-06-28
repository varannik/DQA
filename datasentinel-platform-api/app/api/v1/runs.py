from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.core.config import settings
from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user, require_scope
from app.core.tenancy import resolve_tenant_id
from app.models import DQARun, DQAViolation, Dataset, AuditLog
from app.schemas import RunCreate, RunOut
from app.services.dqa_orchestrator import execute_dqa_run
from app.services.job_dispatcher import publish_dqa_run

router = APIRouter()


def _execute_dqa_background(run_id: str):
    db = SessionLocal()
    try:
        execute_dqa_run(db, run_id)
    finally:
        db.close()


@router.post("/", response_model=RunOut, status_code=status.HTTP_202_ACCEPTED)
def create_run(
    data: RunCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    _=Depends(require_scope("dqa:run")),
):
    dataset = db.query(Dataset).filter(Dataset.id == data.dataset_id).first()
    if not dataset:
        raise HTTPException(404, "Dataset not found")
    tenant_id = resolve_tenant_id(db, dataset.tenant_id)
    run = DQARun(
        tenant_id=tenant_id,
        dataset_id=data.dataset_id,
        project_id=data.project_id,
        triggered_by=user.id,
        status="queued",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    db.add(
        AuditLog(
            event_type="dqa_run_triggered",
            entity_type="dqa_run",
            entity_id=run.id,
            actor_id=user.id,
            actor_role=user.role,
            event_metadata={
                "dataset_id": str(data.dataset_id),
                "project_id": str(data.project_id),
                "tenant_id": str(tenant_id),
                "execution_mode": settings.DQA_EXECUTION_MODE,
            },
        )
    )
    db.commit()

    if settings.DQA_EXECUTION_MODE == "sqs":
        publish_dqa_run(db, run, dataset, user)
    else:
        background_tasks.add_task(_execute_dqa_background, str(run.id))

    return run


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    r = db.query(DQARun).filter(DQARun.id == run_id).first()
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@router.get("/dataset/{dataset_id}", response_model=List[RunOut])
def runs_for_dataset(
    dataset_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)
):
    return (
        db.query(DQARun)
        .filter(DQARun.dataset_id == dataset_id)
        .order_by(DQARun.triggered_at.desc())
        .limit(20)
        .all()
    )


@router.get("/{run_id}/violations")
def run_violations(run_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    viols = db.query(DQAViolation).filter(DQAViolation.run_id == run_id).all()
    return [
        {
            "id": str(v.id),
            "rule_id": v.rule_id,
            "rule_name": v.rule_name,
            "dimension": v.dimension,
            "severity": v.severity,
            "affected_field": v.affected_field,
            "record_count": v.record_count,
            "violation_detail": v.violation_detail,
            "status": v.status,
            "created_at": v.created_at.isoformat(),
        }
        for v in viols
    ]


@router.get("/{run_id}/report")
def run_report(run_id: UUID, db: Session = Depends(get_db), user=Depends(get_current_user)):
    run = db.query(DQARun).filter(DQARun.id == run_id).first()
    if not run:
        raise HTTPException(404, "Run not found")
    viols = db.query(DQAViolation).filter(DQAViolation.run_id == run_id).all()
    return {
        "run_id": str(run_id),
        "status": run.status,
        "triggered_at": run.triggered_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "rules_executed": run.rules_executed,
        "gate_passed": run.gate_passed,
        "readiness_score": run.readiness_score,
        "dimension_scores": run.dimension_scores,
        "total_violations": run.total_violations,
        "violations_by_severity": {
            sev: sum(1 for v in viols if v.severity == sev)
            for sev in ["critical", "high", "medium", "low"]
        },
        "violations_by_dimension": {
            dim: sum(1 for v in viols if v.dimension == dim)
            for dim in set(v.dimension for v in viols)
        },
        "violations": [
            {
                "rule_id": v.rule_id,
                "dimension": v.dimension,
                "severity": v.severity,
                "affected_field": v.affected_field,
                "record_count": v.record_count,
            }
            for v in viols
        ],
    }
