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

import pytest


@pytest.fixture(autouse=True)
def _test_paths(tmp_path, monkeypatch):
    """Route ``DATABASE_URL`` and ``UPLOAD_FOLDER`` to a per-test temp dir."""
    db_path = tmp_path / "test.db"
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir(exist_ok=True)

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("UPLOAD_FOLDER", str(uploads_dir))


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

    db_mod._engine = None

    original_create_app = main_mod.create_app

    def _create_app_with_bootstrap(*args, **kwargs):
        app_instance = original_create_app(*args, **kwargs)
        db_mod.init_db(app_instance.state.engine)
        return app_instance

    monkeypatch.setattr(main_mod, "create_app", _create_app_with_bootstrap)
    try:
        yield
    finally:
        db_mod._engine = None
