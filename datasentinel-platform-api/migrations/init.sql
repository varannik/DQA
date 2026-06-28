-- DataSentinel — PostgreSQL Schema
-- Run automatically on first postgres container start

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ── Tenants ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    full_name VARCHAR(255),
    hashed_password VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'analyst',
    is_active BOOLEAN DEFAULT TRUE,
    last_login TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Projects ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    domain VARCHAR(100) DEFAULT 'co2_sequestration',
    config JSONB DEFAULT '{}',
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

-- ── Datasets ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS datasets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) DEFAULT 'csv',
    row_count INTEGER,
    column_count INTEGER,
    columns_meta JSONB DEFAULT '[]',
    storage_path VARCHAR(500),
    s3_uri VARCHAR(500),
    ingested_by UUID REFERENCES users(id),
    ingested_at TIMESTAMPTZ DEFAULT NOW(),
    status VARCHAR(50) DEFAULT 'ready'
);

-- ── DQA Rules ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dqa_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    rule_id VARCHAR(50) NOT NULL,
    rule_name VARCHAR(255) NOT NULL,
    dimension VARCHAR(50) NOT NULL,
    description TEXT,
    what_it_checks TEXT,
    severity VARCHAR(20) DEFAULT 'medium',
    is_hard_gate BOOLEAN DEFAULT FALSE,
    weight DECIMAL(5,4) DEFAULT 0.125,
    parameters JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── DQA Runs ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dqa_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    dataset_id UUID REFERENCES datasets(id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id),
    triggered_by UUID REFERENCES users(id),
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'queued',
    rules_executed INTEGER DEFAULT 0,
    total_violations INTEGER DEFAULT 0,
    readiness_score DECIMAL(5,4),
    dimension_scores JSONB DEFAULT '{}',
    gate_passed BOOLEAN,
    error_message TEXT
);

-- ── DQA Violations ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS dqa_violations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    run_id UUID REFERENCES dqa_runs(id) ON DELETE CASCADE,
    dataset_id UUID REFERENCES datasets(id),
    rule_id VARCHAR(50) NOT NULL,
    rule_name VARCHAR(255),
    dimension VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    affected_field VARCHAR(255),
    affected_rows JSONB DEFAULT '[]',
    record_count INTEGER DEFAULT 0,
    violation_detail JSONB DEFAULT '{}',
    confidence_score DECIMAL(5,4) DEFAULT 1.0,
    status VARCHAR(50) DEFAULT 'open',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Correction Rules ───────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS correction_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    target_dqa_rule_id VARCHAR(50),
    correction_type VARCHAR(100) NOT NULL,
    correction_logic JSONB DEFAULT '{}',
    priority INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Correction Suggestions ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS correction_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    violation_id UUID REFERENCES dqa_violations(id) ON DELETE CASCADE,
    dataset_id UUID REFERENCES datasets(id),
    suggestion_source VARCHAR(50) NOT NULL,
    original_value JSONB,
    suggested_value JSONB,
    correction_method VARCHAR(100),
    confidence_score DECIMAL(5,4) DEFAULT 0.0,
    explanation TEXT,
    model_version VARCHAR(100),
    feature_importance JSONB DEFAULT '{}',
    status VARCHAR(50) DEFAULT 'pending',
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMPTZ,
    override_value JSONB,
    override_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Approved Corrections ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS approved_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    suggestion_id UUID REFERENCES correction_suggestions(id),
    dataset_id UUID REFERENCES datasets(id),
    field_name VARCHAR(255),
    affected_rows JSONB DEFAULT '[]',
    original_value JSONB,
    corrected_value JSONB,
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMPTZ DEFAULT NOW(),
    applied_to_production BOOLEAN DEFAULT FALSE,
    applied_at TIMESTAMPTZ
);

-- ── AI Training Feedback ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ai_training_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    correction_id UUID REFERENCES approved_corrections(id),
    dataset_id UUID REFERENCES datasets(id),
    project_id UUID REFERENCES projects(id),
    field_name VARCHAR(255),
    error_type VARCHAR(100),
    feature_vector JSONB DEFAULT '{}',
    target_value JSONB,
    used_in_training BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Audit Log ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100),
    entity_id UUID,
    actor_id UUID REFERENCES users(id),
    actor_role VARCHAR(50),
    before_state JSONB,
    after_state JSONB,
    event_metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_violations_run_id ON dqa_violations(run_id);
CREATE INDEX IF NOT EXISTS idx_violations_dataset ON dqa_violations(dataset_id);
CREATE INDEX IF NOT EXISTS idx_violations_status ON dqa_violations(status);
CREATE INDEX IF NOT EXISTS idx_suggestions_violation ON correction_suggestions(violation_id);
CREATE INDEX IF NOT EXISTS idx_suggestions_status ON correction_suggestions(status);
CREATE INDEX IF NOT EXISTS idx_runs_dataset ON dqa_runs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_log(entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);

-- ── Seed: default tenant ────────────────────────────────────────────────────
INSERT INTO tenants (id, name, slug)
VALUES (
    '00000000-0000-4000-8000-000000000001',
    'Default Tenant',
    'default'
) ON CONFLICT (slug) DO NOTHING;

-- ── Seed: default admin user (password: admin123) ─────────────────────────
INSERT INTO users (email, full_name, hashed_password, role)
VALUES (
    'admin@datasentinel.io',
    'System Admin',
    'PLACEHOLDER_RESET_ON_STARTUP',  -- startup.py replaces this with correct argon2 hash
    'admin'
) ON CONFLICT (email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password;

-- ── Seed: demo project ────────────────────────────────────────────────────
INSERT INTO projects (tenant_id, name, description, domain, config)
VALUES (
    '00000000-0000-4000-8000-000000000001',
    'CO₂ Sequestration — Stream 1',
    'Fabric-Native Platform DQA — DQA-STR1-TDD-001',
    'co2_sequestration',
    '{"batch_frequency_minutes": 120, "expected_rows_per_batch": 60, "sla_threshold_seconds": 300, "min_data_coverage": 0.85, "dimension_weights": {"completeness": 0.15, "integrity": 0.20, "timeliness": 0.10, "uniqueness": 0.10, "accuracy": 0.20, "consistency": 0.15, "relevance": 0.10}}'
) ON CONFLICT DO NOTHING;
