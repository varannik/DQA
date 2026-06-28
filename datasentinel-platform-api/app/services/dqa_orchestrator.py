"""DQA run orchestration — shared by BackgroundTasks today, SQS dispatch in platform-api."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from app.engines.dqa.engine import DQAEngine
from app.models import AuditLog, Dataset, DQARule, DQARun, DQAViolation
from app.services.storage import get_dataset_store


def rules_to_dicts(rules: List[DQARule]) -> List[Dict[str, Any]]:
    return [
        {
            "rule_id": r.rule_id,
            "rule_name": r.rule_name,
            "dimension": r.dimension,
            "severity": r.severity,
            "is_hard_gate": r.is_hard_gate,
            "weight": r.weight,
            "parameters": r.parameters,
            "is_active": r.is_active,
        }
        for r in rules
    ]


def persist_dqa_result(db: Session, run: DQARun, result: Dict[str, Any]) -> None:
    for v_data in result["violations"]:
        db.add(
            DQAViolation(
                run_id=run.id,
                dataset_id=run.dataset_id,
                tenant_id=run.tenant_id,
                rule_id=v_data["rule_id"],
                rule_name=v_data["rule_name"],
                dimension=v_data["dimension"],
                severity=v_data["severity"],
                affected_field=v_data["affected_field"],
                affected_rows=v_data["affected_rows"][:200],
                record_count=v_data["record_count"],
                violation_detail=v_data["violation_detail"],
                confidence_score=v_data["confidence_score"],
                status="open",
            )
        )
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    run.rules_executed = result["rules_executed"]
    run.total_violations = len(result["violations"])
    run.readiness_score = result.get("readiness_score", 0)
    run.dimension_scores = result.get("dimension_scores", {})
    run.gate_passed = result.get("gate_passed", False)
    run.error_message = result.get("gate_reason")
    db.add(
        AuditLog(
            event_type="dqa_run_completed",
            entity_type="dqa_run",
            entity_id=run.id,
            actor_id=run.triggered_by,
            actor_role="system",
            after_state={
                "readiness_score": run.readiness_score,
                "total_violations": run.total_violations,
            },
        )
    )
    db.commit()


def execute_dqa_run(db: Session, run_id: str) -> None:
    run = db.query(DQARun).filter(DQARun.id == run_id).first()
    if not run:
        return

    try:
        run.status = "running"
        db.commit()

        dataset = db.query(Dataset).filter(Dataset.id == run.dataset_id).first()
        if not dataset:
            raise FileNotFoundError(f"Dataset not found for run {run_id}")

        store = get_dataset_store()
        df = store.load_df(store.resolve_uri(dataset))

        rules = (
            db.query(DQARule)
            .filter(DQARule.project_id == run.project_id, DQARule.is_active == True)
            .all()
        )
        result = DQAEngine().run(df, rules_to_dicts(rules))
        persist_dqa_result(db, run, result)
    except Exception as e:
        run.status = "failed"
        run.error_message = str(e)
        run.completed_at = datetime.utcnow()
        try:
            db.commit()
        except Exception:
            pass
