BEGIN;

CREATE TABLE IF NOT EXISTS workspace_membership_scope_backfill_audit (
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  invitation_id UUID NOT NULL,
  previous_scope TEXT NOT NULL CHECK (previous_scope IN ('tenant', 'project_bridge')),
  new_scope TEXT NOT NULL CHECK (new_scope IN ('tenant', 'project_bridge')),
  reason TEXT NOT NULL CHECK (reason = 'legacy_project_invitation'),
  evidence_jsonb JSONB NOT NULL DEFAULT '{}'::JSONB,
  migrated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, user_id),
  CHECK (previous_scope <> new_scope)
);

REVOKE ALL ON workspace_membership_scope_backfill_audit FROM PUBLIC;
REVOKE ALL ON workspace_membership_scope_backfill_audit FROM mirofish_app;

WITH earliest_project_acceptance AS (
  SELECT DISTINCT ON (invitation.tenant_id, invitation.accepted_by)
    invitation.tenant_id,
    invitation.accepted_by AS user_id,
    invitation.invitation_id,
    invitation.created_at AS invitation_created_at,
    invitation.accepted_at
  FROM collaboration_invitations AS invitation
  WHERE invitation.project_id IS NOT NULL
    AND invitation.status = 'accepted'
    AND invitation.accepted_by IS NOT NULL
    AND invitation.accepted_at IS NOT NULL
  ORDER BY invitation.tenant_id, invitation.accepted_by, invitation.accepted_at, invitation.invitation_id
), confirmed_legacy_project_bridges AS (
  SELECT
    membership.tenant_id,
    membership.user_id,
    project_invitation.invitation_id,
    membership.access_scope AS previous_scope,
    jsonb_build_object(
      'membership_created_at', membership.created_at,
      'membership_joined_at', membership.joined_at,
      'invitation_created_at', project_invitation.invitation_created_at,
      'invitation_accepted_at', project_invitation.accepted_at
    ) AS evidence_jsonb
  FROM tenant_memberships AS membership
  JOIN earliest_project_acceptance AS project_invitation
    ON project_invitation.tenant_id = membership.tenant_id
   AND project_invitation.user_id = membership.user_id
  WHERE membership.access_scope = 'tenant'
    AND membership.role = 'viewer'
    AND membership.created_at >= project_invitation.invitation_created_at
    AND membership.created_at BETWEEN project_invitation.accepted_at - INTERVAL '5 minutes'
                                  AND project_invitation.accepted_at + INTERVAL '5 minutes'
    AND membership.joined_at BETWEEN project_invitation.accepted_at - INTERVAL '5 minutes'
                                 AND project_invitation.accepted_at + INTERVAL '5 minutes'
    AND NOT EXISTS (
      SELECT 1
      FROM collaboration_invitations AS workspace_invitation
      WHERE workspace_invitation.tenant_id = membership.tenant_id
        AND workspace_invitation.accepted_by = membership.user_id
        AND workspace_invitation.project_id IS NULL
        AND workspace_invitation.status = 'accepted'
    )
)
INSERT INTO workspace_membership_scope_backfill_audit (
  tenant_id,
  user_id,
  invitation_id,
  previous_scope,
  new_scope,
  reason,
  evidence_jsonb
)
SELECT
  candidate.tenant_id,
  candidate.user_id,
  candidate.invitation_id,
  candidate.previous_scope,
  'project_bridge',
  'legacy_project_invitation',
  candidate.evidence_jsonb
FROM confirmed_legacy_project_bridges AS candidate
ON CONFLICT (tenant_id, user_id) DO NOTHING;

UPDATE tenant_memberships AS membership
SET access_scope = audit.new_scope,
    role = 'viewer',
    updated_at = now()
FROM workspace_membership_scope_backfill_audit AS audit
WHERE audit.tenant_id = membership.tenant_id
  AND audit.user_id = membership.user_id
  AND audit.reason = 'legacy_project_invitation'
  AND membership.access_scope = audit.previous_scope;

COMMIT;
