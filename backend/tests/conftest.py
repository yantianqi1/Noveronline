"""Shared pytest fixtures for backend tests.

Why this exists:
    Most tests construct a FastAPI app via ``create_app(settings=_settings(tmp_path))``
    and wrap it in ``TestClient(app)`` *without* the context-manager form
    (``with TestClient(app) as client:``). FastAPI's lifespan — which is where
    ``init_db()`` runs — only fires inside the context-manager form. As a
    result, tables are never created on the per-test engine and every DB-backed
    test fails with ``sqlite3.OperationalError: no such table: …``.

What these fixtures do:
    1. ``_test_paths`` (function autouse) points ``DATABASE_URL`` /
       ``UPLOAD_FOLDER`` at a *per-test* temp directory. Tests that pass
       an explicit ``settings=_settings(tmp_path)`` still override these via
       Pydantic; the env-var defaults only protect bare ``create_app()`` calls
       and the module-level ``app.main.app`` instance from hitting the real
       ``./data/mirofish.db`` or ``backend/uploads``.

       Function-scoping is critical: several tables (e.g. ``chapter_content``)
       have single-column primary keys that would collide across tests sharing
       a session-wide database. A fresh tmp DB per test removes that coupling.

    2. ``_unified_db_bootstrap`` (function autouse) resets the module-level
       ``app.database._engine`` cache and monkey-patches ``app.main.create_app``
       so every app returned has ``init_db(app.state.engine)`` invoked
       synchronously at construction time. This makes the schema available
       regardless of whether the caller enters the TestClient context.

Scope:
    Test-infrastructure only. No service or application code is modified;
    the monkey-patches unwind at the end of each test.
"""

from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# Golden harness opt-in
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--run-golden",
        action="store_true",
        default=False,
        help="run @pytest.mark.golden tests (otherwise skipped)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "golden: prompt-evaluation harness; opt-in via --run-golden or SEED_GOLDEN=1",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-golden") or os.environ.get("SEED_GOLDEN") == "1":
        return
    skip_marker = pytest.mark.skip(
        reason="golden harness disabled by default; use --run-golden or SEED_GOLDEN=1"
    )
    for item in items:
        if "golden" in item.keywords:
            item.add_marker(skip_marker)


def _golden_real_llm_active() -> bool:
    """True when the golden harness is asked to call the real LLM.

    In that mode the per-test sqlite/uploads sandbox below is bypassed so
    LlmRouter sees the user's configured DATABASE_URL and module bindings.
    """
    return os.environ.get("SEED_GOLDEN_REAL_LLM") == "1"


@pytest.fixture(autouse=True)
def _test_paths(tmp_path, monkeypatch):
    """Route ``DATABASE_URL`` and ``UPLOAD_FOLDER`` to a per-test temp dir."""
    if _golden_real_llm_active():
        return
    db_path = tmp_path / "test.db"
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_FOLDER", str(uploads_dir))
    # Tests run many seed pipelines in the same process; default to OFF so
    # the inline graph build in GlobalDataLinker doesn't contaminate the
    # TaskManager singleton used by explicit /build-graph tests. Tests that
    # want to exercise the auto-link path can monkeypatch this back to
    # "true" (see tests/test_global_data_linker.py).
    monkeypatch.setenv("SEED_AUTO_LINK_GLOBAL_DATA", "false")
    # Skip startup backfill in tests — it would fire on every create_app()
    # call and pollute test state.
    monkeypatch.setenv("GLOBAL_DATA_BACKFILL_ON_STARTUP", "false")


@pytest.fixture(autouse=True)
def _unified_db_bootstrap(monkeypatch):
    """Bootstrap the unified database for every test that builds an app.

    Resets ``app.database._engine`` so a stale engine from a prior test can't
    leak via ``get_engine()``, then wraps ``app.main.create_app`` so that
    ``init_db()`` runs synchronously on the fresh engine attached to
    ``app.state.engine``.

    A ``yield + finally`` teardown also force-resets ``_engine`` to ``None``
    after the test, independent of ``monkeypatch``'s undo behavior. Without
    this, a test that writes through ``ProjectManager.save_project_json``
    (which triggers ``get_engine()`` auto-bootstrap against a tmp DB) can
    leave ``_engine`` bound to a database file whose tmp directory gets
    removed by pytest's cleanup — the next test then sees "no such table"
    / "database is locked" errors against the dangling handle.
    """
    import app.database as db_mod
    import app.main as main_mod

    if _golden_real_llm_active():
        # Golden real-LLM mode wants the user's actual DB and engine; do not
        # reset or wrap anything.
        yield
        return

    db_mod._engine = None

    original_create_app = main_mod.create_app

    def _create_app_with_bootstrap(*args, **kwargs):
        app_instance = original_create_app(*args, **kwargs)
        db_mod.init_db(app_instance.state.engine)
        return app_instance

    monkeypatch.setattr(main_mod, "create_app", _create_app_with_bootstrap)

    # Also clear the TaskManager singleton so every test starts with a fresh
    # instance (and a fresh _loop / _task_lock). Without this reset, the
    # singleton's cached event loop can point to a closed asyncio.run() loop
    # from a previous test, causing run_coroutine_threadsafe() futures in
    # later tests to raise CancelledError mid-build.
    try:
        from app.models.task import TaskManager as _TaskManager

        _TaskManager._instance = None
    except Exception:
        pass

    try:
        yield
    finally:
        db_mod._engine = None
        try:
            from app.models.task import TaskManager as _TaskManager

            _TaskManager._instance = None
        except Exception:
            pass
