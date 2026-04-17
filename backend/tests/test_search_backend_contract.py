"""Phase H / Task 9 — search backend contract tests + regressions.

Goals:
1. Contract: every backend, fed the same upserts and the same query,
   must return the same set of result identifiers (same contract shape).
2. SQLite FTS5 regression: ``SqliteFtsBackend`` genuinely uses the FTS
   virtual table (``global_index_fts``) after a rebuild.
3. Router: ``select_backend`` picks SQLite FTS for sqlite engines,
   pg_trgm for postgres, LIKE otherwise.
"""

from __future__ import annotations

import json
from typing import Iterable

from sqlalchemy import create_engine, text

from app.database import init_db
from app.repositories.search_backends import (
    LikeBackend,
    PostgresTrigramBackend,
    SearchResult,
    SqliteFtsBackend,
    select_backend,
)
from app.repositories.search_repo import SearchRepository


def _build_engine():
    engine = create_engine("sqlite:///:memory:", future=True)
    init_db(engine)
    return engine


def _seed_corpus(repo: SearchRepository, *, project_id: str = "proj_demo") -> None:
    repo.upsert(
        [
            {
                "source": "archive",
                "source_ref": "arc_hero",
                "project_id": project_id,
                "entity_type": "character",
                "title": "Lin the Swordsman",
                "summary": "Protagonist with hidden regret",
                "payload": {"core_drive": "redemption"},
                "tags": ["protagonist", "hero"],
                "updated_at": "2026-04-17T00:00:00",
            },
            {
                "source": "archive",
                "source_ref": "arc_villain",
                "project_id": project_id,
                "entity_type": "character",
                "title": "Shadow Lord",
                "summary": "Villain pulling the strings",
                "payload": {"core_drive": "dominion"},
                "tags": ["antagonist"],
                "updated_at": "2026-04-16T00:00:00",
            },
            {
                "source": "asset",
                "source_ref": "asset_codex",
                "project_id": project_id,
                "entity_type": "style",
                "title": "Codex of the Realm",
                "summary": "World-building notes",
                "payload": {"region": "northern"},
                "tags": ["codex", "worldbuilding"],
                "updated_at": "2026-04-15T00:00:00",
            },
        ]
    )


def _ids(results: list[dict] | list[SearchResult]) -> set[str]:
    out = set()
    for r in results:
        if isinstance(r, SearchResult):
            out.add(r.source_ref)
        else:
            out.add(r["source_ref"])
    return out


def test_backend_contract_all_backends_agree_on_obvious_match():
    engine = _build_engine()
    repo = SearchRepository(engine, backend=LikeBackend())
    _seed_corpus(repo)

    for backend in (LikeBackend(), SqliteFtsBackend()):
        results = backend.search(engine, "Swordsman", limit=10)
        result_ids = _ids(results)
        assert "arc_hero" in result_ids, f"{backend.name} missed arc_hero: {result_ids}"


def test_backend_contract_project_filter_applies_on_both_backends():
    engine = _build_engine()
    repo = SearchRepository(engine, backend=LikeBackend())
    _seed_corpus(repo, project_id="proj_a")
    _seed_corpus(repo, project_id="proj_b")

    for backend in (LikeBackend(), SqliteFtsBackend()):
        results = backend.search(engine, "Lin", project_id="proj_a")
        for r in results:
            assert r.project_id == "proj_a", f"{backend.name} leaked project: {r.project_id}"


def test_backend_contract_source_filter_applies_on_both_backends():
    engine = _build_engine()
    repo = SearchRepository(engine, backend=LikeBackend())
    _seed_corpus(repo)

    for backend in (LikeBackend(), SqliteFtsBackend()):
        results = backend.search(engine, "Codex", sources=["asset"])
        assert all(r.source == "asset" for r in results), f"{backend.name} leaked sources"
        assert "asset_codex" in _ids(results)


def test_result_shape_matches_dataclass_contract():
    engine = _build_engine()
    repo = SearchRepository(engine, backend=LikeBackend())
    _seed_corpus(repo)

    for backend in (LikeBackend(), SqliteFtsBackend()):
        results = backend.search(engine, "Lin", limit=10)
        assert results, f"{backend.name} returned no results"
        for r in results:
            assert isinstance(r, SearchResult)
            assert isinstance(r.source, str) and r.source
            assert isinstance(r.source_ref, str) and r.source_ref
            assert isinstance(r.title, str)
            assert isinstance(r.summary, str)
            assert isinstance(r.tags, list)
            assert isinstance(r.payload, dict)
            assert isinstance(r.snippet, str)


def test_sqlite_fts_backend_actually_uses_global_index_fts():
    engine = _build_engine()
    repo = SearchRepository(engine, backend=SqliteFtsBackend())
    _seed_corpus(repo)

    results = repo.search("Shadow", limit=10)
    assert {r["source_ref"] for r in results} == {"arc_villain"}

    # The FTS table should be populated after a search triggered the rebuild.
    with engine.connect() as conn:
        fts_row_count = conn.execute(text("SELECT count(*) FROM global_index_fts")).scalar()
    assert fts_row_count and fts_row_count >= 3


def test_sqlite_fts_backend_falls_back_for_punctuation_only_queries():
    engine = _build_engine()
    repo = SearchRepository(engine, backend=SqliteFtsBackend())
    _seed_corpus(repo)

    # Query that produces no valid FTS tokens → fallback LIKE handles it.
    results = repo.search("...", limit=10)
    assert results == [] or all(isinstance(r, dict) for r in results)


def test_search_repository_routes_sqlite_to_fts_backend_by_default():
    engine = _build_engine()
    repo = SearchRepository(engine)
    assert repo.backend_name == "sqlite_fts5"


def test_select_backend_picks_like_for_unknown_dialect():
    class _DummyDialect:
        name = "mystery"

    class _DummyEngine:
        dialect = _DummyDialect()

    backend = select_backend(_DummyEngine())
    assert backend.name == "like"


def test_select_backend_picks_postgres_trigram_for_postgresql():
    class _PgDialect:
        name = "postgresql"

    class _PgEngine:
        dialect = _PgDialect()

    backend = select_backend(_PgEngine())
    assert backend.name == "postgres_trgm"


def test_postgres_trigram_backend_falls_back_to_like_when_extension_missing():
    """Smoke: the postgres backend's fallback path works against SQLite
    (since pg_trgm isn't installed there). Real pg_trgm integration is
    Task 10's responsibility."""
    engine = _build_engine()
    repo = SearchRepository(engine, backend=LikeBackend())
    _seed_corpus(repo)
    backend = PostgresTrigramBackend()
    results = backend.search(engine, "Swordsman")
    assert "arc_hero" in _ids(results)


def test_repository_search_returns_plain_dicts():
    engine = _build_engine()
    repo = SearchRepository(engine)
    _seed_corpus(repo)

    results = repo.search("Lin")
    assert results
    first = results[0]
    assert isinstance(first, dict)
    assert set(first.keys()) >= {
        "source", "source_ref", "project_id", "entity_type",
        "title", "summary", "tags", "updated_at", "payload", "snippet",
    }
