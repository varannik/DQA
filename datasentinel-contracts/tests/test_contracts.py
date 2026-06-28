from datetime import datetime, timedelta, timezone

from datasentinel_contracts.events.base import AuditContext
from datasentinel_contracts.events.dqa import DqaRunCompleted, DqaRunRequested
from datasentinel_contracts.events.signing import attach_signature, verify_payload


def test_dqa_run_requested_round_trip():
    now = datetime.now(timezone.utc)
    req = DqaRunRequested(
        job_id="550e8400-e29b-41d4-a716-446655440000",
        correlation_id="660e8400-e29b-41d4-a716-446655440001",
        tenant_id="770e8400-e29b-41d4-a716-446655440002",
        project_id="880e8400-e29b-41d4-a716-446655440003",
        dataset_id="990e8400-e29b-41d4-a716-446655440004",
        dataset_uri="s3://bucket/tenants/t/datasets/d.csv",
        audit_context=AuditContext(requested_by="user-1"),
        issued_at=now,
        expires_at=now + timedelta(minutes=15),
        rules_snapshot=[],
    )
    secret = "test-secret"
    signed = attach_signature(req.model_dump(mode="json"), secret)
    payload = {k: v for k, v in signed.items() if k != "signature"}
    assert verify_payload(payload, signed["signature"], secret)
    restored = DqaRunRequested.model_validate(signed)
    assert restored.event_type == "dqa.run.requested"


def test_dqa_run_completed_sign_verify():
    completed = DqaRunCompleted(
        job_id="550e8400-e29b-41d4-a716-446655440000",
        correlation_id="660e8400-e29b-41d4-a716-446655440001",
        tenant_id="770e8400-e29b-41d4-a716-446655440002",
        status="completed",
        gate_passed=False,
        readiness_score=0.725,
        dimension_scores={"integrity": 0.85},
        rules_executed=28,
        violations_s3_uri="s3://bucket/violations.json",
    )
    secret = "test-secret"
    signed = attach_signature(completed.model_dump(mode="json"), secret)
    payload = {k: v for k, v in signed.items() if k != "signature"}
    assert verify_payload(payload, signed["signature"], secret)
