from __future__ import annotations

import os
import subprocess
from pathlib import Path


INFRA = Path(__file__).resolve().parents[1]
SCRIPT = INFRA / "scripts" / "cleanup-local-test-fixtures.sh"


def _fake_psql(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "psql"
    executable.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "$@" > "$CAPTURE_ARGS"\n'
        'cat > "$CAPTURE_SQL"\n'
        'printf " mode | category | row_count\\n preview | users | 0\\n"\n',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "CAPTURE_ARGS": str(tmp_path / "args.txt"),
        "CAPTURE_SQL": str(tmp_path / "input.sql"),
        "MIROFISH_FIXTURE_CLEANUP_DATABASE_URL": "postgresql://fixture@127.0.0.1:54329/mirofish",
        "MIROFISH_DEPLOYMENT_ENV": "local",
    }
    return bin_dir, env


def test_cleanup_defaults_to_preview_for_explicit_loopback_database(tmp_path: Path) -> None:
    _, env = _fake_psql(tmp_path)

    result = subprocess.run([str(SCRIPT)], env=env, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    assert "mode=preview" in result.stdout
    assert "rolled back" in result.stdout
    assert "cleanup_apply=0" in (tmp_path / "args.txt").read_text(encoding="utf-8")
    sql = (tmp_path / "input.sql").read_text(encoding="utf-8")
    assert "BEGIN ISOLATION LEVEL SERIALIZABLE;" in sql
    assert "ROLLBACK;" in sql


def test_cleanup_apply_is_an_explicit_psql_variable(tmp_path: Path) -> None:
    _, env = _fake_psql(tmp_path)

    result = subprocess.run([str(SCRIPT), "--apply"], env=env, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr
    assert "mode=apply" in result.stdout
    assert "cleanup committed" in result.stdout
    assert "cleanup_apply=1" in (tmp_path / "args.txt").read_text(encoding="utf-8")


def test_cleanup_refuses_remote_database_before_invoking_psql(tmp_path: Path) -> None:
    _, env = _fake_psql(tmp_path)
    env["MIROFISH_FIXTURE_CLEANUP_DATABASE_URL"] = "postgresql://fixture@db.example.test/mirofish"

    result = subprocess.run([str(SCRIPT), "--apply"], env=env, text=True, capture_output=True)

    assert result.returncode != 0
    assert "explicit loopback PostgreSQL database" in result.stderr
    assert not (tmp_path / "args.txt").exists()


def test_cleanup_refuses_libpq_query_routing_overrides(tmp_path: Path) -> None:
    for query in (
        "hostaddr=203.0.113.10",
        "host=db.example.test",
        "service=remote-db",
        "dbname=other_database",
    ):
        case_path = tmp_path / query.split("=", 1)[0]
        case_path.mkdir()
        _, env = _fake_psql(case_path)
        env["MIROFISH_FIXTURE_CLEANUP_DATABASE_URL"] = (
            f"postgresql://fixture@localhost/mirofish?{query}"
        )

        result = subprocess.run([str(SCRIPT), "--apply"], env=env, text=True, capture_output=True)

        assert result.returncode != 0
        assert "explicit loopback PostgreSQL database" in result.stderr
        assert not Path(env["CAPTURE_ARGS"]).exists()


def test_cleanup_refuses_production_even_for_loopback_database(tmp_path: Path) -> None:
    _, env = _fake_psql(tmp_path)
    env["MIROFISH_DEPLOYMENT_ENV"] = "production"

    result = subprocess.run([str(SCRIPT), "--apply"], env=env, text=True, capture_output=True)

    assert result.returncode != 0
    assert "disabled for production" in result.stderr
    assert not (tmp_path / "args.txt").exists()


def test_compose_mode_requires_explicit_local_environment(tmp_path: Path) -> None:
    _, env = _fake_psql(tmp_path)
    env.pop("MIROFISH_FIXTURE_CLEANUP_DATABASE_URL")
    env.pop("MIROFISH_DEPLOYMENT_ENV")

    result = subprocess.run([str(SCRIPT)], env=env, text=True, capture_output=True)

    assert result.returncode != 0
    assert "MIROFISH_DEPLOYMENT_ENV=local" in result.stderr
    assert not (tmp_path / "args.txt").exists()


def test_sql_uses_exact_allowlists_and_protects_personal_workspace() -> None:
    encoded = SCRIPT.read_text(encoding="utf-8")

    for protected in (
        "admin@qq.com",
        "10000000-0000-0000-0000-000000000001",
        "10000000-0000-0000-0000-000000000101",
        "10000000-0000-0000-0000-000000000201",
    ):
        assert protected in encoded
    assert "cleanup_fixture_tenants" in encoded
    assert "cleanup_fixture_users" in encoded
    assert "expected_slug = tenant.slug" in encoded
    assert "expected_email = lower(app_user.email)" in encoded
    assert "ILIKE" not in encoded.upper()
    assert "fixture marker validation failed" in encoded
    assert "protected_admin_stale_sessions" not in encoded
    assert encoded.count("DELETE FROM user_sessions") == 1

    for fixture_marker in (
        "27000000-0000-4000-8000-000000000001",
        "27000000-0000-4000-8000-000000000003",
        "27000000-0000-4000-8000-000000000011",
        "27000000-0000-4000-8000-000000000014",
        "collab-live",
        "collab-foreign",
        "owner@example.test",
        "suspended@example.test",
    ):
        assert fixture_marker in encoded

    sessions = encoded.index("DELETE FROM user_sessions")
    projects = encoded.index("DELETE FROM projects")
    workspaces = encoded.index("DELETE FROM tenants")
    users = encoded.index("DELETE FROM users")
    assert sessions < projects < workspaces < users
    assert "BEGIN ISOLATION LEVEL SERIALIZABLE;" in encoded
    assert "COMMIT;" in encoded
    assert "ROLLBACK;" in encoded
