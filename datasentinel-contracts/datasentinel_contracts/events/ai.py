from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from datasentinel_contracts.events.base import JobEnvelope
from datasentinel_contracts.events.correction import ViolationSnapshot


class AiPredictRequested(JobEnvelope):
    event_type: Literal["ai.predict.requested"] = "ai.predict.requested"
    run_id: str
    dataset_id: str
    dataset_uri: str
    violations_snapshot: List[ViolationSnapshot] = Field(default_factory=list)
    feedback_s3_uri: Optional[str] = None


class AiTrainingTriggered(JobEnvelope):
    event_type: Literal["ai.training.triggered"] = "ai.training.triggered"
    field_name: str
    error_type: str
    feedback_s3_uri: str
    sample_count: int


class AiPredictCompleted(BaseModel):
    schema_version: str = "1.0"
    event_type: Literal["ai.predict.completed"] = "ai.predict.completed"
    job_id: str
    correlation_id: str
    tenant_id: str
    run_id: str
    status: Literal["completed", "failed"]
    suggestions_s3_uri: Optional[str] = None
    suggestion_count: int = 0
    error_message: Optional[str] = None
    signature: Optional[str] = None

    def payload_for_signing(self) -> dict:
        return self.model_dump(mode="json", exclude={"signature"})
