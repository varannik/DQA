from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from datasentinel_contracts.events.base import JobEnvelope, RuleSnapshot


class CorrectionRuleSnapshot(BaseModel):
    id: str
    name: str
    target_dqa_rule_id: Optional[str] = None
    correction_type: str
    correction_logic: Dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    is_active: bool = True


class ViolationSnapshot(BaseModel):
    id: str
    rule_id: str
    dimension: str
    severity: str
    affected_field: Optional[str] = None
    affected_rows: List[Any] = Field(default_factory=list)
    violation_detail: Dict[str, Any] = Field(default_factory=dict)


class CorrectionRequested(JobEnvelope):
    event_type: Literal["correction.requested"] = "correction.requested"
    run_id: str
    dataset_id: str
    dataset_uri: str
    violations_s3_uri: Optional[str] = None
    violations_snapshot: List[ViolationSnapshot] = Field(default_factory=list)
    correction_rules_snapshot: List[CorrectionRuleSnapshot] = Field(default_factory=list)


class CorrectionCompleted(BaseModel):
    schema_version: str = "1.0"
    event_type: Literal["correction.completed"] = "correction.completed"
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
