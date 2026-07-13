BEGIN;

CREATE TABLE IF NOT EXISTS collaboration_invitations (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  invitation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID,
  email_normalized TEXT NOT NULL CHECK (email_normalized = lower(btrim(email_normalized)) AND email_normalized <> ''),
  tenant_role TEXT CHECK (tenant_role IN ('owner', 'admin', 'editor', 'writer', 'viewer', 'billing')),
  project_role TEXT CHECK (project_role IN ('project_owner', 'editor', 'writer', 'analyst', 'viewer')),
  token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'revoked', 'expired')),
  delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (delivery_status IN ('pending', 'delivered', 'failed', 'not_configured')),
  invited_by UUID NOT NULL REFERENCES users(user_id),
  accepted_by UUID REFERENCES users(user_id),
  request_id TEXT,
  delivery_attempts INTEGER NOT NULL DEFAULT 0 CHECK (delivery_attempts >= 0),
  last_delivery_error_code TEXT,
  expires_at TIMESTAMPTZ NOT NULL,
  accepted_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  last_sent_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CHECK (
    (project_id IS NULL AND tenant_role IS NOT NULL AND project_role IS NULL) OR
    (project_id IS NOT NULL AND tenant_role IS NULL AND project_role IS NOT NULL)
  ),
  FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, project_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_collaboration_invites_active_tenant
ON collaboration_invitations (tenant_id, email_normalized)
WHERE project_id IS NULL AND status = 'pending';

CREATE UNIQUE INDEX IF NOT EXISTS idx_collaboration_invites_active_project
ON collaboration_invitations (tenant_id, project_id, email_normalized)
WHERE project_id IS NOT NULL AND status = 'pending';

CREATE INDEX IF NOT EXISTS idx_collaboration_invites_scope_status
ON collaboration_invitations (tenant_id, project_id, status, expires_at DESC);

CREATE TABLE IF NOT EXISTS collaboration_delivery_attempts (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  delivery_attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  invitation_id UUID NOT NULL REFERENCES collaboration_invitations(invitation_id) ON DELETE CASCADE,
  channel TEXT NOT NULL DEFAULT 'email' CHECK (channel = 'email'),
  status TEXT NOT NULL CHECK (status IN ('delivered', 'failed', 'not_configured')),
  provider_message_id TEXT,
  error_code TEXT,
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_collaboration_delivery_invitation
ON collaboration_delivery_attempts (tenant_id, invitation_id, attempted_at DESC);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  reset_token_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'consumed', 'revoked', 'expired')),
  delivery_status TEXT NOT NULL DEFAULT 'pending' CHECK (delivery_status IN ('pending', 'delivered', 'failed', 'not_configured')),
  request_id TEXT,
  delivery_attempts INTEGER NOT NULL DEFAULT 0 CHECK (delivery_attempts >= 0),
  last_delivery_error_code TEXT,
  expires_at TIMESTAMPTZ NOT NULL,
  consumed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_password_reset_active_user
ON password_reset_tokens (user_id) WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_password_reset_expiry
ON password_reset_tokens (status, expires_at);

CREATE TABLE IF NOT EXISTS password_reset_delivery_attempts (
  delivery_attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  reset_token_id UUID NOT NULL REFERENCES password_reset_tokens(reset_token_id) ON DELETE CASCADE,
  channel TEXT NOT NULL DEFAULT 'email' CHECK (channel = 'email'),
  status TEXT NOT NULL CHECK (status IN ('delivered', 'failed', 'not_configured')),
  provider_message_id TEXT,
  error_code TEXT,
  attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS auth_security_audit_logs (
  auth_audit_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  actor_user_id UUID REFERENCES users(user_id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id UUID,
  request_id TEXT,
  metadata_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_auth_security_audit_user_created
ON auth_security_audit_logs (user_id, created_at DESC);

-- Token acceptance needs to discover the tenant before an RLS transaction can be opened.
-- The function returns no token material and only matches an exact SHA-256 digest.
CREATE OR REPLACE FUNCTION collaboration_invitation_tenant_for_token(p_token_hash TEXT)
RETURNS UUID
LANGUAGE sql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
  SELECT tenant_id
  FROM collaboration_invitations
  WHERE token_hash = p_token_hash
  LIMIT 1
$$;

REVOKE ALL ON FUNCTION collaboration_invitation_tenant_for_token(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION collaboration_invitation_tenant_for_token(TEXT) TO mirofish_app;

ALTER TABLE collaboration_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE collaboration_invitations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_collaboration_invitations ON collaboration_invitations;
CREATE POLICY tenant_isolation_collaboration_invitations
ON collaboration_invitations FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

ALTER TABLE collaboration_delivery_attempts ENABLE ROW LEVEL SECURITY;
ALTER TABLE collaboration_delivery_attempts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_collaboration_delivery_attempts ON collaboration_delivery_attempts;
CREATE POLICY tenant_isolation_collaboration_delivery_attempts
ON collaboration_delivery_attempts FOR ALL
USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID)
WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

GRANT SELECT, INSERT, UPDATE, DELETE ON collaboration_invitations TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON collaboration_delivery_attempts TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_tokens TO mirofish_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset_delivery_attempts TO mirofish_app;
REVOKE SELECT ON auth_security_audit_logs FROM mirofish_app;
GRANT INSERT ON auth_security_audit_logs TO mirofish_app;

COMMIT;
