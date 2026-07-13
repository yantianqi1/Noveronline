BEGIN;

INSERT INTO llm_quota_policies (
  tenant_id,
  scope_type,
  project_id,
  module_key,
  token_limit,
  concurrency_limit,
  period_seconds,
  enabled,
  updated_by
)
SELECT
  tenant.tenant_id,
  'tenant',
  NULL,
  NULL,
  5000000,
  8,
  2592000,
  TRUE,
  NULL
FROM tenants AS tenant
WHERE NOT EXISTS (
  SELECT 1
  FROM llm_quota_policies AS policy
  WHERE policy.tenant_id = tenant.tenant_id
    AND policy.scope_type = 'tenant'
    AND policy.enabled = TRUE
);

COMMIT;