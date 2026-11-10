from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "infra" / "scripts" / "run-live-test-stack.sh"
COMPOSE = ROOT / "infra" / "docker-compose.yml"
GO_GUARD = ROOT / "apps" / "api" / "internal" / "testschema" / "schema.go"
PYTHON_GUARD = ROOT / "apps" / "agent-runtime" / "tests" / "live_schema_guard.py"
WEB_GUARD = ROOT / "apps" / "web" / "scripts" / "live-test-database.mjs"
ASSET_BROWSER = ROOT / "apps" / "web" / "tests" / "asset-detail-browser-live.test.mjs"
PI_LIVE = ROOT / "apps" / "pi-agent-runtime" / "src" / "runtime" / "pi-writer-live-e2e.test.ts"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_live_test_runner_uses_unique_stack_marker_and_volume_teardown() -> None:
    runner = _text(RUNNER)

    assert 'COMPOSE_PROJECT_NAME="mirofish-saas-live-$run_id"' in runner
    assert 'POSTGRES_DB="mirofish_test_$run_id"' in runner
    assert "ALTER DATABASE" in runner
    assert "mirofish.live_test" in runner
    assert "down -v --remove-orphans" in runner
    assert "trap cleanup EXIT HUP INT TERM" in runner
    assert "/mirofish?" not in runner


def test_all_shared_guards_reject_runtime_database_without_disposable_marker() -> None:
    for guard in (_text(GO_GUARD), _text(PYTHON_GUARD), _text(WEB_GUARD)):
        assert "mirofish_test_" in guard
        assert "mirofish.live_test" in guard or guard == _text(WEB_GUARD)
        assert "refusing" in guard or "disposable" in guard


def test_browser_fixture_no_longer_targets_the_main_compose_database() -> None:
    browser = _text(ASSET_BROWSER)

    assert "disposableLiveDatabaseConfig" in browser
    assert "mirofish.live_test" in browser
    assert "mirofish-saas-postgres-1" not in browser
    assert "127.0.0.1:54329/mirofish" not in browser
    assert "liveDatabase.runtimeUrl" in browser


def test_temporal_cors_origin_is_stack_configurable() -> None:
    assert "${TEMPORAL_CORS_ORIGINS:-http://localhost:3999}" in _text(COMPOSE)


def test_pi_live_fixture_requires_the_disposable_database_marker() -> None:
    live_test = _text(PI_LIVE)
    assert "current_database()" in live_test
    assert "mirofish.live_test" in live_test
    assert "^mirofish_test_" in live_test


def test_app_stack_includes_workers_required_by_api_readiness() -> None:
    runner = _text(RUNNER)
    app_start = runner.split('if [ "$start_app" -eq 1 ]; then', 1)[1].split("\nfi", 1)[0]
    assert app_start.rstrip().endswith("up -d --build --wait")
    assert "--wait api web" not in app_start


def test_each_migration_has_a_restart_sentinel_and_runner_owned_ledger() -> None:
    bootstrap = _text(ROOT / "infra" / "scripts" / "bootstrap-compose-database.sh")
    for migration in (ROOT / "infra" / "postgres" / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"):
        assert f"{migration.name[:4]}_*)" in bootstrap, f"Missing restart sentinel: {migration.name}"
        assert "INSERT INTO mirofish_schema_migrations" not in _text(migration), migration.name


def test_fresh_stack_creates_runtime_role_before_granting_ledger_access() -> None:
    bootstrap = _text(ROOT / "infra" / "scripts" / "bootstrap-compose-database.sh")
    assert bootstrap.index("CREATE ROLE %I LOGIN") < bootstrap.index("GRANT SELECT ON mirofish_schema_migrations")


def test_api_build_image_satisfies_the_module_go_version() -> None:
    module = _text(ROOT / "apps" / "api" / "go.mod")
    dockerfile = _text(ROOT / "infra" / "docker" / "api.Dockerfile")
    required = re.search(r"^go (\d+)\.(\d+)", module, re.MULTILINE)
    supplied = re.search(r"FROM golang:(\d+)\.(\d+)", dockerfile)
    assert required and supplied
    assert tuple(map(int, supplied.groups())) >= tuple(map(int, required.groups()))
