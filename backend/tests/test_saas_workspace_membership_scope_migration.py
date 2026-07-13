from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "infra" / "postgres" / "migrations" / "0015_workspace_membership_scope.sql"
ROLLBACK = ROOT / "infra" / "postgres" / "rollbacks" / "0015_workspace_membership_scope.sql"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_workspace_membership_scope_distinguishes_full_and_project_only_access() -> None:
    sql = _sql(MIGRATION)
    assert "ADD COLUMN IF NOT EXISTS access_scope TEXT NOT NULL DEFAULT 'tenant'" in sql
    assert "access_scope IN ('tenant', 'project_bridge')" in sql
    assert "idx_tenant_memberships_user_scope" in sql


def test_project_bridge_rls_requires_an_active_matching_project_membership() -> None:
    sql = _sql(MIGRATION)
    assert "DROP POLICY IF EXISTS current_user_membership_select_projects ON projects" in sql
    assert "tm.access_scope = 'tenant'" in sql
    assert "pm.project_id = projects.project_id" in sql
    assert "pm.user_id = tm.user_id" in sql
    assert "pm.status = 'active'" in sql


def test_workspace_scope_rollback_restores_original_project_membership_policy() -> None:
    sql = _sql(ROLLBACK)
    assert "DROP COLUMN IF EXISTS access_scope" in sql
    assert "CREATE POLICY current_user_membership_select_projects" in sql
    assert "tm.status = 'active'" in sql
    assert "project_bridge" not in sql
