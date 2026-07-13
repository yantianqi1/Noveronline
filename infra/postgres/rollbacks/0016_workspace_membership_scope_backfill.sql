BEGIN;

UPDATE tenant_memberships AS membership
SET access_scope = audit.previous_scope,
    updated_at = now()
FROM workspace_membership_scope_backfill_audit AS audit
WHERE audit.tenant_id = membership.tenant_id
  AND audit.user_id = membership.user_id
  AND membership.access_scope = audit.new_scope;

DROP TABLE workspace_membership_scope_backfill_audit;

COMMIT;
