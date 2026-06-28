-- Migration 002: multi-tenancy + s3_uri (existing deployments)
CREATE TABLE IF NOT EXISTS tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO tenants (id, name, slug)
VALUES ('00000000-0000-4000-8000-000000000001', 'Default Tenant', 'default')
ON CONFLICT (slug) DO NOTHING;

ALTER TABLE projects ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE datasets ADD COLUMN IF NOT EXISTS s3_uri VARCHAR(500);
ALTER TABLE dqa_runs ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE dqa_violations ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE correction_rules ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE correction_suggestions ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE approved_corrections ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);
ALTER TABLE ai_training_feedback ADD COLUMN IF NOT EXISTS tenant_id UUID REFERENCES tenants(id);

UPDATE projects SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
UPDATE datasets SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
UPDATE dqa_runs SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
UPDATE dqa_violations SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
UPDATE correction_rules SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
UPDATE correction_suggestions SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
UPDATE approved_corrections SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
UPDATE ai_training_feedback SET tenant_id = '00000000-0000-4000-8000-000000000001' WHERE tenant_id IS NULL;
