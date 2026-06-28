from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any, Dict
from datetime import datetime
from uuid import UUID

# ── Auth ──────────────────────────────────────────────────────────────────────
class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict

class UserCreate(BaseModel):
    email: EmailStr
    full_name: str
    password: str
    role: str = "analyst"

class UserOut(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime
    class Config: from_attributes = True

# ── Projects ──────────────────────────────────────────────────────────────────
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None
    domain: str = "co2_sequestration"
    config: Dict[str, Any] = {}

class ProjectOut(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    domain: str
    config: Dict[str, Any]
    created_at: datetime
    is_active: bool
    class Config: from_attributes = True

# ── Datasets ──────────────────────────────────────────────────────────────────
class DatasetOut(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    source_type: str
    row_count: Optional[int]
    column_count: Optional[int]
    columns_meta: List[Any]
    status: str
    ingested_at: datetime
    class Config: from_attributes = True

# ── Rules ─────────────────────────────────────────────────────────────────────
class RuleCreate(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    description: Optional[str] = None
    what_it_checks: Optional[str] = None
    severity: str = "medium"
    is_hard_gate: bool = False
    weight: float = 0.125
    parameters: Dict[str, Any] = {}

class RuleUpdate(BaseModel):
    severity: Optional[str] = None
    is_active: Optional[bool] = None
    parameters: Optional[Dict[str, Any]] = None
    weight: Optional[float] = None

class RuleOut(BaseModel):
    id: UUID
    project_id: UUID
    rule_id: str
    rule_name: str
    dimension: str
    description: Optional[str]
    what_it_checks: Optional[str]
    severity: str
    is_hard_gate: bool
    weight: float
    parameters: Dict[str, Any]
    is_active: bool
    created_at: datetime
    class Config: from_attributes = True

# ── Runs ──────────────────────────────────────────────────────────────────────
class RunCreate(BaseModel):
    dataset_id: UUID
    project_id: UUID

class RunOut(BaseModel):
    id: UUID
    dataset_id: UUID
    project_id: UUID
    status: str
    rules_executed: int
    total_violations: int
    readiness_score: Optional[float]
    dimension_scores: Dict[str, Any]
    gate_passed: Optional[bool]
    triggered_at: datetime
    completed_at: Optional[datetime]
    error_message: Optional[str]
    class Config: from_attributes = True

# ── Violations ────────────────────────────────────────────────────────────────
class ViolationOut(BaseModel):
    id: UUID
    run_id: UUID
    rule_id: str
    rule_name: Optional[str]
    dimension: str
    severity: str
    affected_field: Optional[str]
    affected_rows: List[Any]
    record_count: int
    violation_detail: Dict[str, Any]
    confidence_score: float
    status: str
    created_at: datetime
    class Config: from_attributes = True

# ── Corrections ───────────────────────────────────────────────────────────────
class CorrectionRuleCreate(BaseModel):
    name: str
    target_dqa_rule_id: Optional[str] = None
    correction_type: str
    correction_logic: Dict[str, Any] = {}
    priority: int = 100

class SuggestionOut(BaseModel):
    id: UUID
    violation_id: UUID
    suggestion_source: str
    original_value: Optional[Any]
    suggested_value: Optional[Any]
    correction_method: Optional[str]
    confidence_score: float
    explanation: Optional[str]
    model_version: Optional[str]
    feature_importance: Dict[str, Any]
    status: str
    created_at: datetime
    class Config: from_attributes = True

class ApprovalAction(BaseModel):
    suggestion_id: UUID
    override_value: Optional[Any] = None
    override_reason: Optional[str] = None

class BulkApproval(BaseModel):
    suggestion_ids: List[UUID]

# ── Audit ─────────────────────────────────────────────────────────────────────
class AuditOut(BaseModel):
    id: UUID
    event_type: str
    entity_type: Optional[str]
    entity_id: Optional[UUID]
    actor_id: Optional[UUID]
    actor_role: Optional[str]
    event_metadata: Dict[str, Any]
    created_at: datetime
    class Config: from_attributes = True
