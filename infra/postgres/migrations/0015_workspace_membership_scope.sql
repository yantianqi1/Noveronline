BEGIN;

ALTER TABLE tenant_memberships
ADD COLUMN IF NOT EXISTS access_scope TEXT NOT NULL DEFAULT 'tenant';

ALTER TABLE tenant_memberships
DROP CONSTRAINT IF EXISTS tenant_memberships_access_scope_check;

ALTER TABLE tenant_memberships
ADD CONSTRAINT tenant_memberships_access_scope_check
CHECK (access_scope IN ('tenant', 'project_bridge'));

CREATE INDEX IF NOT EXISTS idx_tenant_memberships_user_scope
ON tenant_memberships (user_id, access_scope, status, tenant_id);

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
      AND (
        tm.access_scope = 'tenant'
        OR EXISTS (
          SELECT 1
          FROM project_members pm
          WHERE pm.tenant_id = projects.tenant_id
            AND pm.project_id = projects.project_id
            AND pm.user_id = tm.user_id
            AND pm.status = 'active'
        )
      )
  )
);

COMMIT;
