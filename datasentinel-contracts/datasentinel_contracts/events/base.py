from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class AuditContext(BaseModel):
    requested_by: str
    requested_by_type: Literal["user", "client", "system"] = "user"
    client_id: Optional[str] = None
    source: str = "platform-api"


class SignedEnvelope(BaseModel):
    schema_version: str = "1.0"
    signature: Optional[str] = None

    def payload_for_signing(self) -> dict:
        data = self.model_dump(mode="json", exclude={"signature"})
        return data


class RuleSnapshot(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    severity: str = "medium"
    is_hard_gate: bool = False
    weight: float = 0.125
    parameters: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class JobEnvelope(SignedEnvelope):
    job_id: str
    correlation_id: str
    tenant_id: str
    project_id: str
    audit_context: AuditContext
    issued_at: datetime
    expires_at: datetime
