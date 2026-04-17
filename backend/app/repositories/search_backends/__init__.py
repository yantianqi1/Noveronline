"""Pluggable search backends for the unified search repository.

``SearchRepository`` delegates the read path to a backend selected by
``engine.dialect``. On SQLite the ``SqliteFtsBackend`` uses the FTS5
virtual table ``global_index_fts``; on PostgreSQL the
``PostgresTrigramBackend`` is wired for ``pg_trgm`` similarity queries.
A portable ``LikeBackend`` is the fallback when neither path applies.

All backends share the :class:`SearchBackend` contract so the caller
sees an identical result shape regardless of the underlying dialect.
"""

from __future__ import annotations

from .base import SearchBackend, SearchResult
from .like_search import LikeBackend
from .postgres_search import PostgresTrigramBackend
from .sqlite_search import SqliteFtsBackend


def select_backend(engine) -> SearchBackend:
    """Pick a backend based on the SQLAlchemy dialect name."""
    dialect = engine.dialect.name
    if dialect == "sqlite":
        return SqliteFtsBackend()
    if dialect == "postgresql":
        return PostgresTrigramBackend()
    return LikeBackend()


__all__ = [
    "LikeBackend",
    "PostgresTrigramBackend",
    "SearchBackend",
    "SearchResult",
    "SqliteFtsBackend",
    "select_backend",
]
