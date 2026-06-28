from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ViolationRecord(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    severity: str
    affected_field: str
    affected_rows: List[int] = Field(default_factory=list)
    record_count: int = 0
    violation_detail: Dict[str, Any] = Field(default_factory=dict)
    confidence_score: float = 1.0


class ViolationsPayload(BaseModel):
    violations: List[ViolationRecord] = Field(default_factory=list)
