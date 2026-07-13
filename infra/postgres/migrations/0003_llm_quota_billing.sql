BEGIN;

ALTER TABLE llm_channels
ADD COLUMN IF NOT EXISTS external_provider_opt_in BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS llm_quota_policies (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type TEXT NOT NULL CHECK (scope_type IN ('tenant', 'project', 'module')),
  project_id UUID,
  module_key TEXT,
  token_limit BIGINT CHECK (token_limit IS NULL OR token_limit >= 0),
  cost_limit_micros BIGINT CHECK (cost_limit_micros IS NULL OR cost_limit_micros >= 0),
  concurrency_limit INTEGER CHECK (concurrency_limit IS NULL OR concurrency_limit > 0),
  period_seconds INTEGER NOT NULL CHECK (period_seconds > 0),
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  updated_by UUID REFERENCES users(user_id),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (scope_type = 'tenant' AND project_id IS NULL AND module_key IS NULL) OR
    (scope_type = 'project' AND project_id IS NOT NULL AND module_key IS NULL) OR
    (scope_type = 'module' AND project_id IS NOT NULL AND NULLIF(BTRIM(module_key), '') IS NOT NULL)
  ),
  CHECK (token_limit IS NOT NULL OR cost_limit_micros IS NOT NULL OR concurrency_limit IS NOT NULL),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_quota_policies_scope
ON llm_quota_policies (
  tenant_id,
  scope_type,
  COALESCE(project_id, '00000000-0000-0000-0000-000000000000'::UUID),
  COALESCE(module_key, '')
);

CREATE INDEX IF NOT EXISTS idx_llm_quota_policies_resolution
ON llm_quota_policies (tenant_id, project_id, module_key, enabled);

CREATE TABLE IF NOT EXISTS llm_quota_reservations (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  reservation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_call_id TEXT NOT NULL,
  project_id UUID NOT NULL,
  run_id UUID,
  module_key TEXT NOT NULL,
  channel_id UUID NOT NULL REFERENCES llm_channels(channel_id) ON DELETE RESTRICT,
  model_id TEXT NOT NULL,
  reserved_tokens BIGINT NOT NULL CHECK (reserved_tokens >= 0),
  reserved_cost_micros BIGINT NOT NULL CHECK (reserved_cost_micros >= 0),
  actual_prompt_tokens BIGINT CHECK (actual_prompt_tokens IS NULL OR actual_prompt_tokens >= 0),
  actual_completion_tokens BIGINT CHECK (actual_completion_tokens IS NULL OR actual_completion_tokens >= 0),
  actual_cost_micros BIGINT CHECK (actual_cost_micros IS NULL OR actual_cost_micros >= 0),
  status TEXT NOT NULL DEFAULT 'reserved' CHECK (status IN ('reserved', 'finalized', 'released', 'expired')),
  expires_at TIMESTAMPTZ NOT NULL,
  finalized_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, provider_call_id),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_llm_quota_reservations_active
ON llm_quota_reservations (tenant_id, project_id, module_key, expires_at)
WHERE status = 'reserved';

ALTER TABLE llm_quota_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_quota_policies FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_llm_quota_policies ON llm_quota_policies;
CREATE POLICY tenant_isolation_llm_quota_policies
ON llm_quota_policies
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE llm_quota_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_quota_reservations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_llm_quota_reservations ON llm_quota_reservations;
CREATE POLICY tenant_isolation_llm_quota_reservations
ON llm_quota_reservations
FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

GRANT SELECT, INSERT, UPDATE, DELETE ON llm_quota_policies TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON llm_quota_reservations TO mirofish_app;

COMMIT;
