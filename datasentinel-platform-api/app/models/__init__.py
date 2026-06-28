import uuid
from sqlalchemy import Column, String, Boolean, DateTime, Integer, Float, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255))
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="analyst")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Project(Base):
    __tablename__ = "projects"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    domain = Column(String(100), default="co2_sequestration")
    config = Column(JSONB, default={})
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    datasets = relationship("Dataset", back_populates="project", lazy="dynamic")
    rules = relationship("DQARule", back_populates="project", lazy="dynamic")

class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    name = Column(String(255), nullable=False)
    source_type = Column(String(50), default="csv")
    row_count = Column(Integer)
    column_count = Column(Integer)
    columns_meta = Column(JSONB, default=[])
    storage_path = Column(String(500))
    s3_uri = Column(String(500))
    ingested_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    ingested_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(50), default="ready")
    project = relationship("Project", back_populates="datasets")

class DQARule(Base):
    __tablename__ = "dqa_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    rule_id = Column(String(50), nullable=False)
    rule_name = Column(String(255), nullable=False)
    dimension = Column(String(50), nullable=False)
    description = Column(Text)
    what_it_checks = Column(Text)
    severity = Column(String(20), default="medium")
    is_hard_gate = Column(Boolean, default=False)
    weight = Column(Float, default=0.125)
    parameters = Column(JSONB, default={})
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    project = relationship("Project", back_populates="rules")

class DQARun(Base):
    __tablename__ = "dqa_runs"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    triggered_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(50), default="queued")
    rules_executed = Column(Integer, default=0)
    total_violations = Column(Integer, default=0)
    readiness_score = Column(Float)
    dimension_scores = Column(JSONB, default={})
    gate_passed = Column(Boolean)
    error_message = Column(Text)
    violations = relationship("DQAViolation", back_populates="run", lazy="dynamic")

class DQAViolation(Base):
    __tablename__ = "dqa_violations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    run_id = Column(UUID(as_uuid=True), ForeignKey("dqa_runs.id"))
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    rule_id = Column(String(50), nullable=False)
    rule_name = Column(String(255))
    dimension = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    affected_field = Column(String(255))
    affected_rows = Column(JSONB, default=[])
    record_count = Column(Integer, default=0)
    violation_detail = Column(JSONB, default={})
    confidence_score = Column(Float, default=1.0)
    status = Column(String(50), default="open")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    run = relationship("DQARun", back_populates="violations")
    suggestions = relationship("CorrectionSuggestion", back_populates="violation", lazy="dynamic")

class CorrectionRule(Base):
    __tablename__ = "correction_rules"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    name = Column(String(255), nullable=False)
    target_dqa_rule_id = Column(String(50))
    correction_type = Column(String(100), nullable=False)
    correction_logic = Column(JSONB, default={})
    priority = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class CorrectionSuggestion(Base):
    __tablename__ = "correction_suggestions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    violation_id = Column(UUID(as_uuid=True), ForeignKey("dqa_violations.id"))
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    suggestion_source = Column(String(50), nullable=False)
    original_value = Column(JSONB)
    suggested_value = Column(JSONB)
    correction_method = Column(String(100))
    confidence_score = Column(Float, default=0.0)
    explanation = Column(Text)
    model_version = Column(String(100))
    feature_importance = Column(JSONB, default={})
    status = Column(String(50), default="pending")
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at = Column(DateTime(timezone=True))
    override_value = Column(JSONB)
    override_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    violation = relationship("DQAViolation", back_populates="suggestions")

class ApprovedCorrection(Base):
    __tablename__ = "approved_corrections"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    suggestion_id = Column(UUID(as_uuid=True), ForeignKey("correction_suggestions.id"))
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    field_name = Column(String(255))
    affected_rows = Column(JSONB, default=[])
    original_value = Column(JSONB)
    corrected_value = Column(JSONB)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at = Column(DateTime(timezone=True), server_default=func.now())
    applied_to_production = Column(Boolean, default=False)
    applied_at = Column(DateTime(timezone=True))

class AITrainingFeedback(Base):
    __tablename__ = "ai_training_feedback"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    correction_id = Column(UUID(as_uuid=True), ForeignKey("approved_corrections.id"))
    dataset_id = Column(UUID(as_uuid=True), ForeignKey("datasets.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    field_name = Column(String(255))
    error_type = Column(String(100))
    feature_vector = Column(JSONB, default={})
    target_value = Column(JSONB)
    used_in_training = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type = Column(String(100), nullable=False)
    entity_type = Column(String(100))
    entity_id = Column(UUID(as_uuid=True))
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    actor_role = Column(String(50))
    before_state = Column(JSONB)
    after_state = Column(JSONB)
    event_metadata = Column(JSONB, default={})
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ApiClient(Base):
    __tablename__ = "api_clients"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(String(100), unique=True, nullable=False)
    hashed_secret = Column(String(255), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    scopes = Column(JSONB, default=[])
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Webhook(Base):
    __tablename__ = "webhooks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    url = Column(String(500), nullable=False)
    events = Column(JSONB, default=["dqa.run.completed"])
    secret = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
