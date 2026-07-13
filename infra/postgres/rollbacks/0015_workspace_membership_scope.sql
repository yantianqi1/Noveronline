BEGIN;

DROP POLICY IF EXISTS current_user_membership_select_projects ON projects;
CREATE POLICY current_user_membership_select_projects
ON projects
FOR SELECT
USING (
  EXISTS (
    SELECT 1
    FROM tenant_memberships tm
    WHERE tm.tenant_id = projects.tenant_id
      AND tm.user_id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
      AND tm.status = 'active'
  )
);

DROP INDEX IF EXISTS idx_tenant_memberships_user_scope;

ALTER TABLE tenant_memberships
DROP CONSTRAINT IF EXISTS tenant_memberships_access_scope_check;

ALTER TABLE tenant_memberships
DROP COLUMN IF EXISTS access_scope;

COMMIT;
