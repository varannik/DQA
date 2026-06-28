import json
import logging
import os
from datetime import datetime, timezone

from datasentinel_contracts.events.correction import CorrectionCompleted, CorrectionRequested
from datasentinel_contracts.events.signing import attach_signature, verify_payload
from datasentinel_contracts.schemas.suggestion import CorrectionSuggestionRecord, SuggestionsPayload

from app.engine.rules import RuleBasedCorrectionEngine
from app.storage import load_df, save_json, suggestions_uri

logger = logging.getLogger("correction-engine.consumer")
SIGNING_KEY = os.environ.get("INTERNAL_MESSAGE_SIGNING_KEY", "")


def process_message(body: str) -> None:
    data = json.loads(body)
    payload = {k: v for k, v in data.items() if k != "signature"}
    if not verify_payload(payload, data.get("signature", ""), SIGNING_KEY):
        logger.warning("Invalid signature")
        return
    exp = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > exp:
        logger.warning("Expired message")
        return

    req = CorrectionRequested.model_validate(data)
    df = load_df(req.dataset_uri)
    violations = [v.model_dump() for v in req.violations_snapshot]
    rules = [r.model_dump() for r in req.correction_rules_snapshot]
    suggestions = RuleBasedCorrectionEngine().generate(df, violations, rules)

    s_uri = suggestions_uri(req.tenant_id, req.job_id)
    records = [
        CorrectionSuggestionRecord(
            violation_id=s.violation_id,
            suggestion_source=s.suggestion_source,
            original_value=s.original_value,
            suggested_value=s.suggested_value,
            correction_method=s.correction_method,
            confidence_score=s.confidence_score,
            explanation=s.explanation,
            feature_importance=s.feature_importance,
        )
        for s in suggestions
    ]
    save_json(s_uri, SuggestionsPayload(suggestions=records).model_dump(mode="json"))

    completed = CorrectionCompleted(
        job_id=req.job_id,
        correlation_id=req.correlation_id,
        tenant_id=req.tenant_id,
        run_id=req.run_id,
        status="completed",
        suggestions_s3_uri=s_uri,
        suggestion_count=len(records),
    )
    import boto3

    body_out = attach_signature(completed.model_dump(mode="json"), SIGNING_KEY)
    boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1")).send_message(
        QueueUrl=os.environ["SQS_RESULT_URL"],
        MessageBody=json.dumps(body_out),
    )
