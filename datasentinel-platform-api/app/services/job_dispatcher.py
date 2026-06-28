"""Publish signed job envelopes to SQS."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from datasentinel_contracts.events.base import AuditContext, RuleSnapshot
from datasentinel_contracts.events.dqa import DqaRunRequested
from datasentinel_contracts.events.correction import CorrectionRequested, CorrectionRuleSnapshot, ViolationSnapshot
from datasentinel_contracts.events.ai import AiPredictRequested, AiTrainingTriggered

from app.core.config import settings
from app.core.internal_auth import sign_envelope
from app.models import CorrectionRule, Dataset, DQARule, DQARun, DQAViolation

logger = logging.getLogger("datasentinel.dispatcher")


def _sqs_client():
    import boto3

    return boto3.client("sqs", region_name=settings.AWS_REGION)


def _send(queue_url: str, body: dict) -> None:
    if not queue_url:
        logger.warning("SQS queue URL not configured; skipping dispatch")
        return
    _sqs_client().send_message(QueueUrl=queue_url, MessageBody=json.dumps(body))


def _audit_from_user(user) -> AuditContext:
    return AuditContext(
        requested_by=str(user.id),
        requested_by_type="user",
        source="platform-api",
    )


def publish_dqa_run(db, run: DQARun, dataset: Dataset, user) -> None:
    rules = (
        db.query(DQARule)
        .filter(DQARule.project_id == run.project_id, DQARule.is_active == True)
        .all()
    )
    now = datetime.now(timezone.utc)
    store = __import__("app.services.storage", fromlist=["get_dataset_store"]).get_dataset_store()
    req = DqaRunRequested(
        job_id=str(run.id),
        correlation_id=str(uuid.uuid4()),
        tenant_id=str(run.tenant_id),
        project_id=str(run.project_id),
        dataset_id=str(dataset.id),
        dataset_uri=store.resolve_uri(dataset),
        rules_snapshot=[
            RuleSnapshot(
                rule_id=r.rule_id,
                rule_name=r.rule_name,
                dimension=r.dimension,
                severity=r.severity,
                is_hard_gate=r.is_hard_gate,
                weight=float(r.weight or 0.125),
                parameters=r.parameters or {},
                is_active=r.is_active,
            )
            for r in rules
        ],
        audit_context=_audit_from_user(user),
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    _send(settings.SQS_DQA_REQUESTED_URL, sign_envelope(req.model_dump(mode="json")))


def publish_correction_run(db, run: DQARun, dataset: Dataset, user) -> str:
    violations = db.query(DQAViolation).filter(DQAViolation.run_id == run.id).all()
    rules = (
        db.query(CorrectionRule)
        .filter(CorrectionRule.project_id == run.project_id, CorrectionRule.is_active == True)
        .all()
    )
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    store = __import__("app.services.storage", fromlist=["get_dataset_store"]).get_dataset_store()
    req = CorrectionRequested(
        job_id=job_id,
        correlation_id=str(uuid.uuid4()),
        tenant_id=str(run.tenant_id),
        project_id=str(run.project_id),
        run_id=str(run.id),
        dataset_id=str(dataset.id),
        dataset_uri=store.resolve_uri(dataset),
        violations_snapshot=[
            ViolationSnapshot(
                id=str(v.id),
                rule_id=v.rule_id,
                dimension=v.dimension,
                severity=v.severity,
                affected_field=v.affected_field,
                affected_rows=v.affected_rows or [],
                violation_detail=v.violation_detail or {},
            )
            for v in violations
        ],
        correction_rules_snapshot=[
            CorrectionRuleSnapshot(
                id=str(r.id),
                name=r.name,
                target_dqa_rule_id=r.target_dqa_rule_id,
                correction_type=r.correction_type,
                correction_logic=r.correction_logic or {},
                priority=r.priority,
                is_active=r.is_active,
            )
            for r in rules
        ],
        audit_context=_audit_from_user(user),
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
    )
    _send(settings.SQS_CORRECTION_REQUESTED_URL, sign_envelope(req.model_dump(mode="json")))
    return job_id


def publish_ai_training(db, project_id, tenant_id, field_name: str, error_type: str, sample_count: int) -> None:
    now = datetime.now(timezone.utc)
    req = AiTrainingTriggered(
        job_id=str(uuid.uuid4()),
        correlation_id=str(uuid.uuid4()),
        tenant_id=str(tenant_id),
        project_id=str(project_id),
        field_name=field_name,
        error_type=error_type,
        feedback_s3_uri="",
        sample_count=sample_count,
        audit_context=AuditContext(requested_by="system", requested_by_type="system"),
        issued_at=now,
        expires_at=now + timedelta(minutes=60),
    )
    _send(settings.SQS_AI_TRAINING_TRIGGERED_URL, sign_envelope(req.model_dump(mode="json")))
