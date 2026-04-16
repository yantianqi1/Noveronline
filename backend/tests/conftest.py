"""Shared pytest fixtures for backend tests.

Why this exists:
    Most tests construct a FastAPI app via ``create_app(settings=_settings(tmp_path))``
    and wrap it in ``TestClient(app)`` *without* the context-manager form
    (``with TestClient(app) as client:``). FastAPI's lifespan — which is where
    ``init_db()`` runs — only fires inside the context-manager form. As a
    result, tables are never created on the per-test engine and every DB-backed
    test fails with ``sqlite3.OperationalError: no such table: …``.

What these fixtures do:
    1. ``_session_test_paths`` (session autouse) points ``DATABASE_URL`` /
       ``UPLOAD_FOLDER`` at a session-scoped temp directory. Tests that pass
       an explicit ``settings=_settings(tmp_path)`` still override these via
       Pydantic; the env-var defaults only protect bare ``create_app()`` calls
       and the module-level ``app.main.app`` instance from hitting the real
       ``./data/mirofish.db`` or ``backend/uploads``.

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


@pytest.fixture(scope="session", autouse=True)
def _session_test_paths(tmp_path_factory):
    """Route ``DATABASE_URL`` and ``UPLOAD_FOLDER`` to a session temp dir."""
    root = tmp_path_factory.mktemp("mirofish_session")
    db_path = root / "session.db"
    uploads_dir = root / "uploads"
    uploads_dir.mkdir()

    previous = {
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "UPLOAD_FOLDER": os.environ.get("UPLOAD_FOLDER"),
    }
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["UPLOAD_FOLDER"] = str(uploads_dir)

    yield

    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


@pytest.fixture(autouse=True)
def _unified_db_bootstrap(monkeypatch):
    """Bootstrap the unified database for every test that builds an app.

    Resets ``app.database._engine`` so a stale engine from a prior test can't
    leak via ``get_engine()``, then wraps ``app.main.create_app`` so that
    ``init_db()`` runs synchronously on the fresh engine attached to
    ``app.state.engine``.
    """
    import app.database as db_mod
    import app.main as main_mod

    monkeypatch.setattr(db_mod, "_engine", None, raising=False)

    original_create_app = main_mod.create_app

    def _create_app_with_bootstrap(*args, **kwargs):
        app_instance = original_create_app(*args, **kwargs)
        db_mod.init_db(app_instance.state.engine)
        return app_instance

    monkeypatch.setattr(main_mod, "create_app", _create_app_with_bootstrap)
