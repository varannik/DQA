import json
import logging
import os
from datetime import datetime, timezone

from datasentinel_contracts.events.ai import AiPredictCompleted, AiPredictRequested, AiTrainingTriggered
from datasentinel_contracts.events.signing import attach_signature, verify_payload
from datasentinel_contracts.schemas.suggestion import CorrectionSuggestionRecord, SuggestionsPayload

from app.engine.predictor import S3ModelRegistry
from app.storage import load_df, load_json, save_json, suggestions_uri

logger = logging.getLogger("ai-engine.consumer")
SIGNING_KEY = os.environ.get("INTERNAL_MESSAGE_SIGNING_KEY", "")
registry = S3ModelRegistry()


def _verify(data: dict) -> bool:
    payload = {k: v for k, v in data.items() if k != "signature"}
    return verify_payload(payload, data.get("signature", ""), SIGNING_KEY)


def process_training(data: dict) -> None:
    req = AiTrainingTriggered.model_validate(data)
    feedback = load_json(req.feedback_s3_uri) if req.feedback_s3_uri else []
    model = registry.train(feedback)
    if model:
        registry.save_model(req.project_id, req.field_name, req.error_type, model)


def process_predict(data: dict) -> None:
    req = AiPredictRequested.model_validate(data)
    df = load_df(req.dataset_uri)
    violations = [v.model_dump() for v in req.violations_snapshot]
    suggestions = []
    for v in violations:
        field = v.get("affected_field", "")
        error_type = v.get("rule_id", "")
        model = registry.load_model(req.project_id, field, error_type)
        if not model:
            continue
        s = registry.predict_single(df, v, model, field, error_type)
        if s:
            suggestions.append(s)

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
    completed = AiPredictCompleted(
        job_id=req.job_id,
        correlation_id=req.correlation_id,
        tenant_id=req.tenant_id,
        run_id=req.run_id,
        status="completed",
        suggestions_s3_uri=s_uri,
        suggestion_count=len(records),
    )
    import boto3

    body = attach_signature(completed.model_dump(mode="json"), SIGNING_KEY)
    boto3.client("sqs", region_name=os.environ.get("AWS_REGION", "eu-west-1")).send_message(
        QueueUrl=os.environ["SQS_RESULT_URL"], MessageBody=json.dumps(body)
    )


def process_message(body: str) -> None:
    data = json.loads(body)
    if not _verify(data):
        return
    exp = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    if datetime.now(timezone.utc) > exp:
        return
    event_type = data.get("event_type")
    if event_type == "ai.training.triggered":
        process_training(data)
    elif event_type == "ai.predict.requested":
        process_predict(data)
