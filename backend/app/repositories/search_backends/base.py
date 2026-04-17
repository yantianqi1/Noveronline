"""Search backend contract + shared helpers."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import Engine


@dataclass
class SearchResult:
    """Single row returned by any backend.

    Kept intentionally flat and JSON-friendly so the search API layer
    can marshal it directly.
    """

    source: str
    source_ref: str
    project_id: str | None
    entity_type: str
    title: str
    summary: str
    tags: list[str]
    updated_at: str
    payload: dict[str, Any]
    snippet: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "source_ref": self.source_ref,
            "project_id": self.project_id,
            "entity_type": self.entity_type,
            "title": self.title,
            "summary": self.summary,
            "tags": list(self.tags),
            "updated_at": self.updated_at,
            "payload": dict(self.payload),
            "snippet": self.snippet,
        }


class SearchBackend(ABC):
    """Every dialect-specific backend implements this contract."""

    name: str = ""

    @abstractmethod
    def search(
        self,
        engine: Engine,
        query: str,
        *,
        project_id: str | None = None,
        sources: Iterable[str] | None = None,
        entity_types: Iterable[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SearchResult]:
        """Return ordered results for the given query and filters."""


def row_to_result(row: dict[str, Any]) -> SearchResult:
    body = row.get("body") or ""
    tags_text = row.get("tags") or ""
    try:
        payload = json.loads(row.get("payload_json") or "{}") or {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    return SearchResult(
        source=row["source"],
        source_ref=row["source_ref"],
        project_id=row.get("project_id"),
        entity_type=row.get("entity_type") or "",
        title=row.get("title") or "",
        summary=body.split("\n", 1)[0],
        tags=tags_text.split() if tags_text else [],
        updated_at=row.get("updated_at") or "",
        payload=payload,
        snippet=body[:96] if body else "",
    )


__all__ = ["SearchBackend", "SearchResult", "row_to_result"]
