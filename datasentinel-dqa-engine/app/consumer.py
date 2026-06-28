"""DQA engine SQS consumer."""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from datasentinel_contracts.events.dqa import DqaRunCompleted, DqaRunRequested
from datasentinel_contracts.events.signing import attach_signature, verify_payload
from datasentinel_contracts.schemas.violation import ViolationRecord, ViolationsPayload

from app.engine.rules import DQAEngine
from app.storage import load_df, save_json, violations_uri

logger = logging.getLogger("dqa-engine.consumer")
SIGNING_KEY = os.environ.get("INTERNAL_MESSAGE_SIGNING_KEY", "")


def _verify(data: dict) -> bool:
    signature = data.get("signature")
    if not signature:
        return False
    payload = {k: v for k, v in data.items() if k != "signature"}
    return verify_payload(payload, signature, SIGNING_KEY)


def _is_expired(data: dict) -> bool:
    expires_at = data.get("expires_at")
    if not expires_at:
        return True
    exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    return datetime.now(timezone.utc) > exp


def process_message(body: str) -> None:
    data = json.loads(body)
    if not _verify(data):
        logger.warning("Rejected message: invalid signature")
        return
    if _is_expired(data):
        logger.warning("Rejected message: expired")
        return

    req = DqaRunRequested.model_validate(data)
    rules = [r.model_dump() for r in req.rules_snapshot]
    df = load_df(req.dataset_uri)
    result = DQAEngine().run(df, rules)

    v_uri = violations_uri(req.tenant_id, req.job_id)
    violations = [ViolationRecord.model_validate(v) for v in result["violations"]]
    save_json(v_uri, ViolationsPayload(violations=violations).model_dump(mode="json"))

    completed = DqaRunCompleted(
        job_id=req.job_id,
        correlation_id=req.correlation_id,
        tenant_id=req.tenant_id,
        status="completed" if result.get("gate_passed") is not None else "completed",
        gate_passed=result.get("gate_passed"),
        readiness_score=result.get("readiness_score"),
        dimension_scores=result.get("dimension_scores") or {},
        rules_executed=result.get("rules_executed", 0),
        violations_s3_uri=v_uri,
        error_message=result.get("gate_reason"),
    )
    _publish_result(completed)


def _publish_result(event: DqaRunCompleted) -> None:
    import boto3

    queue_url = os.environ.get("SQS_RESULT_URL", "")
    if not queue_url:
        logger.error("SQS_RESULT_URL not configured")
        return
    body = attach_signature(event.model_dump(mode="json"), SIGNING_KEY)
    boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1")).send_message(
        QueueUrl=queue_url, MessageBody=json.dumps(body)
    )
