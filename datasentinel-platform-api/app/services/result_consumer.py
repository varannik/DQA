"""Consume engine result events and persist to PostgreSQL."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from datasentinel_contracts.events.correction import CorrectionCompleted
from datasentinel_contracts.events.dqa import DqaRunCompleted
from datasentinel_contracts.schemas.suggestion import SuggestionsPayload
from datasentinel_contracts.schemas.violation import ViolationsPayload

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.internal_auth import verify_envelope
from app.models import AuditLog, CorrectionSuggestion, DQARun, DQAViolation
from app.services.storage import get_dataset_store
from app.services.webhooks import dispatch_webhooks

logger = logging.getLogger("datasentinel.result_consumer")

AI_MIN_SAMPLES = 50


def _persist_dqa_completed(db, event: DqaRunCompleted) -> None:
    run = db.query(DQARun).filter(DQARun.id == event.job_id).first()
    if not run:
        logger.warning("Run %s not found for completed event", event.job_id)
        return
    if run.status == "completed":
        return

    violations = []
    if event.violations_s3_uri:
        store = get_dataset_store()
        if hasattr(store, "load_json"):
            payload = store.load_json(event.violations_s3_uri)
            violations = ViolationsPayload.model_validate(payload).violations
        else:
            logger.error("Cannot load violations from S3 without S3DatasetStore")

    for v in violations:
        db.add(
            DQAViolation(
                run_id=run.id,
                dataset_id=run.dataset_id,
                tenant_id=run.tenant_id,
                rule_id=v.rule_id,
                rule_name=v.rule_name,
                dimension=v.dimension,
                severity=v.severity,
                affected_field=v.affected_field,
                affected_rows=v.affected_rows[:200],
                record_count=v.record_count,
                violation_detail=v.violation_detail,
                confidence_score=v.confidence_score,
                status="open",
            )
        )

    run.status = event.status
    run.completed_at = datetime.utcnow()
    run.rules_executed = event.rules_executed
    run.total_violations = len(violations)
    run.readiness_score = event.readiness_score
    run.dimension_scores = event.dimension_scores or {}
    run.gate_passed = event.gate_passed
    run.error_message = event.error_message
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
    dispatch_webhooks(
        db,
        run.tenant_id,
        "dqa.run.completed",
        {
            "event": "dqa.run.completed",
            "run_id": str(run.id),
            "project_id": str(run.project_id),
            "status": run.status,
            "gate_passed": run.gate_passed,
            "readiness_score": run.readiness_score,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
    )


def _persist_correction_completed(db, event: CorrectionCompleted) -> None:
    run = db.query(DQARun).filter(DQARun.id == event.run_id).first()
    if not run:
        return

    suggestions = []
    if event.suggestions_s3_uri:
        store = get_dataset_store()
        if hasattr(store, "load_json"):
            payload = store.load_json(event.suggestions_s3_uri)
            suggestions = SuggestionsPayload.model_validate(payload).suggestions

    created = 0
    for s in suggestions:
        violation = db.query(DQAViolation).filter(DQAViolation.id == s.violation_id).first()
        if not violation:
            continue
        existing = (
            db.query(CorrectionSuggestion)
            .filter(
                CorrectionSuggestion.violation_id == violation.id,
                CorrectionSuggestion.suggestion_source == s.suggestion_source,
            )
            .first()
        )
        if existing:
            continue
        db.add(
            CorrectionSuggestion(
                tenant_id=run.tenant_id,
                violation_id=violation.id,
                dataset_id=run.dataset_id,
                suggestion_source=s.suggestion_source,
                original_value=s.original_value,
                suggested_value=s.suggested_value,
                correction_method=s.correction_method,
                confidence_score=s.confidence_score,
                explanation=s.explanation,
                feature_importance=s.feature_importance,
                model_version=s.model_version,
                status="pending",
            )
        )
        created += 1
    db.commit()
    logger.info("Persisted %s correction suggestions for run %s", created, event.run_id)


def handle_message(body: str) -> None:
    data = json.loads(body)
    if not verify_envelope(data):
        logger.warning("Rejected result message: invalid signature")
        return

    event_type = data.get("event_type")
    db = SessionLocal()
    try:
        if event_type == "dqa.run.completed":
            _persist_dqa_completed(db, DqaRunCompleted.model_validate(data))
        elif event_type == "correction.completed":
            _persist_correction_completed(db, CorrectionCompleted.model_validate(data))
        else:
            logger.debug("Ignoring event type %s", event_type)
    finally:
        db.close()


def poll_once() -> int:
    if not settings.SQS_DQA_COMPLETED_URL:
        return 0

    import boto3

    sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
    processed = 0
    for queue_url in filter(
        None,
        [
            settings.SQS_DQA_COMPLETED_URL,
            settings.SQS_CORRECTION_COMPLETED_URL,
        ],
    ):
        resp = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=1,
            VisibilityTimeout=120,
        )
        for msg in resp.get("Messages", []):
            try:
                handle_message(msg["Body"])
                sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])
                processed += 1
            except Exception:
                logger.exception("Failed to process SQS message")
    return processed
