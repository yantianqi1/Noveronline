from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0016_workspace_membership_scope_backfill.sql"
ROLLBACK = ROOT / "infra" / "postgres" / "rollbacks" / "0016_workspace_membership_scope_backfill.sql"
BOOTSTRAP = ROOT / "infra" / "scripts" / "bootstrap-compose-database.sh"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_backfill_reclassifies_only_evidenced_legacy_project_invite_memberships() -> None:
    sql = _sql(MIGRATION)

    assert "workspace_membership_scope_backfill_audit" in sql
    assert "invitation.project_id IS NOT NULL" in sql
    assert "invitation.status = 'accepted'" in sql
    assert "membership.access_scope = 'tenant'" in sql
    assert "membership.role = 'viewer'" in sql
    assert "membership.created_at >= project_invitation.invitation_created_at" in sql
    assert "membership.created_at BETWEEN project_invitation.accepted_at - INTERVAL '5 minutes'" in sql
    assert "membership.joined_at BETWEEN project_invitation.accepted_at - INTERVAL '5 minutes'" in sql
    assert "workspace_invitation.project_id IS NULL" in sql
    assert "workspace_invitation.status = 'accepted'" in sql
    assert "AND NOT EXISTS" in sql
    assert "SET access_scope = audit.new_scope" in sql


def test_existing_workspace_member_then_project_invite_is_not_downgraded() -> None:
    sql = _sql(MIGRATION)

    # A pre-existing member predates the project invitation or has an accepted
    # workspace invitation, so either guard excludes it from the backfill.
    assert "membership.created_at >= project_invitation.invitation_created_at" in sql
    assert "workspace_invitation.accepted_by = membership.user_id" in sql
    assert "workspace_invitation.project_id IS NULL" in sql


def test_backfill_has_a_private_audit_sentinel_and_targeted_rollback() -> None:
    migration = _sql(MIGRATION)
    rollback = _sql(ROLLBACK)
    bootstrap = _sql(BOOTSTRAP)

    assert "REVOKE ALL ON workspace_membership_scope_backfill_audit FROM mirofish_app" in migration
    assert "0016_*)" in bootstrap
    assert "workspace_membership_scope_backfill_audit_check" in bootstrap
    assert "grantee = 'mirofish_app'" in bootstrap
    assert "SET access_scope = audit.previous_scope" in rollback
    assert "DROP TABLE workspace_membership_scope_backfill_audit" in rollback
