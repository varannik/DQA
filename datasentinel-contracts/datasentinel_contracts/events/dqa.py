from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from datasentinel_contracts.events.base import AuditContext, JobEnvelope, RuleSnapshot


class DqaRunRequested(JobEnvelope):
    event_type: Literal["dqa.run.requested"] = "dqa.run.requested"
    dataset_id: str
    dataset_uri: str
    rules_snapshot: List[RuleSnapshot] = Field(default_factory=list)


class DqaRunCompleted(BaseModel):
    schema_version: str = "1.0"
    event_type: Literal["dqa.run.completed"] = "dqa.run.completed"
    job_id: str
    correlation_id: str
    tenant_id: str
    status: Literal["completed", "failed"]
    gate_passed: Optional[bool] = None
    readiness_score: Optional[float] = None
    dimension_scores: Dict[str, float] = Field(default_factory=dict)
    rules_executed: int = 0
    violations_s3_uri: Optional[str] = None
    error_message: Optional[str] = None
    signature: Optional[str] = None
    completed_at: datetime = Field(default_factory=datetime.utcnow)

    def payload_for_signing(self) -> dict:
        return self.model_dump(mode="json", exclude={"signature"})
