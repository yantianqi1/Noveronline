"""Manuscript repository backed by project-scoped assets.

Manuscript blocks live as ``asset_type='manuscript_block'`` rows in the
``assets`` table.  Block ordering is stored inside
``payload_json -> '$.block_order'`` (integer with gap=10).

This repository provides basic block CRUD via SQLAlchemy Core.  Higher-level
logic (insert-between re-numbering, chapter tag resolution, FTS search) stays
in :class:`ManuscriptAssetAdapter`.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, cast, delete, func, select, text, update, Integer

from app.tables.assets import assets

from ..schemas.asset_types import AssetType


_BLOCK_TYPE = AssetType.MANUSCRIPT_BLOCK.value

# One raw-SQL statement in this module embeds ``'manuscript_block'`` as a
# literal inside a multi-line ``text()`` query (it also contains a JSON
# literal ``'{}'`` that makes f-string / str.format interpolation fragile).
# This assert couples that literal to the enum so any drift is caught at
# import time.
assert _BLOCK_TYPE == "manuscript_block", (
    f"manuscript_repo raw SQL expects 'manuscript_block' but enum is {_BLOCK_TYPE!r}"
)

from .base import ProjectScopedRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_BLOCK_ORDER_GAP = 10

# Columns safe to update directly on the assets row.
_ALLOWED_TOP_FIELDS = {"content", "summary", "title", "enabled", "pinned", "word_count"}

# Keys safe to update inside payload_json.
_ALLOWED_PAYLOAD_FIELDS = {
    "chapter_id", "chapter_tag", "source_scene_id",
    "open_threads_json", "pov_entity_id", "involved_entities_json",
    "location", "narrative_note", "block_order",
}


def _block_type_clause():
    """Filter predicate for manuscript blocks."""
    return assets.c.asset_type == _BLOCK_TYPE


def _block_order_expr():
    """SQLAlchemy expression to extract block_order from payload_json.

    Uses ``json_extract`` which works with SQLite.  For other backends a
    ``func.json_extract`` call is sufficient because SQLAlchemy renders it
    as-is.
    """
    return cast(
        func.json_extract(assets.c.payload_json, "$.block_order"),
        Integer,
    )


class ManuscriptRepository(ProjectScopedRepository):
    """Basic block CRUD for manuscript blocks in the assets table."""

    def __init__(self, engine: Engine):
        super().__init__(engine, assets)

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    def commit_block(self, project_id: str, values: dict[str, Any]) -> None:
        """Upsert a manuscript block by asset_id.

        *values* must contain ``asset_id``.  The caller is responsible for
        populating ``payload_json`` (or individual payload fields that will be
        merged).
        """
        values.setdefault("asset_type", _BLOCK_TYPE)
        values.setdefault("scope", "project")
        self.upsert_by_keys(project_id, values, ("asset_id",))

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_blocks(
        self,
        project_id: str,
        chapter_id: str | None = None,
        *,
        include_content: bool = True,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """List manuscript blocks ordered by block_order.

        Optionally filter by ``chapter_id`` (stored in ``payload_json``).
        When *include_content* is False the ``content`` column is excluded.
        """
        if include_content:
            cols = [assets]
        else:
            cols = [c for c in assets.c if c.name != "content"]

        clauses = [
            assets.c.project_id == project_id,
            _block_type_clause(),
            assets.c.scope == "project",
        ]
        if chapter_id is not None:
            clauses.append(
                func.json_extract(assets.c.payload_json, "$.chapter_id") == chapter_id
            )

        stmt = (
            select(*cols)
            .where(and_(*clauses))
            .order_by(_block_order_expr())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]

    def get_block(
        self, project_id: str, block_id: str
    ) -> dict[str, Any] | None:
        """Get a single manuscript block by asset_id."""
        stmt = (
            select(assets)
            .where(
                and_(
                    assets.c.project_id == project_id,
                    assets.c.asset_id == block_id,
                    _block_type_clause(),
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update_block(
        self, project_id: str, block_id: str, **kwargs: Any
    ) -> bool:
        """Update allowed fields on a manuscript block.

        Top-level asset columns (content, summary, title, enabled, pinned,
        word_count) are updated directly.  Payload keys (chapter_id,
        chapter_tag, etc.) are merged into ``payload_json``.
        Returns True if a row was matched.
        """
        with self.connect() as conn:
            # Fetch current payload
            row = conn.execute(
                select(assets.c.payload_json).where(
                    and_(
                        assets.c.asset_id == block_id,
                        assets.c.project_id == project_id,
                        _block_type_clause(),
                    )
                )
            ).fetchone()
            if row is None:
                return False

            try:
                payload = json.loads(row[0] or "{}")
            except (json.JSONDecodeError, TypeError):
                payload = {}

            set_clauses: dict[str, Any] = {}

            for k, v in kwargs.items():
                if k in _ALLOWED_TOP_FIELDS:
                    set_clauses[k] = v
                elif k in _ALLOWED_PAYLOAD_FIELDS:
                    payload[k] = v

            # Auto-update word_count when content changes
            if "content" in kwargs:
                set_clauses["word_count"] = len(kwargs["content"] or "")

            set_clauses["payload_json"] = json.dumps(payload, ensure_ascii=False)
            set_clauses["updated_at"] = _now()

            conn.execute(
                update(assets)
                .where(
                    and_(
                        assets.c.asset_id == block_id,
                        assets.c.project_id == project_id,
                        _block_type_clause(),
                    )
                )
                .values(**set_clauses)
            )
            return True

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_block(self, project_id: str, block_id: str) -> int:
        """Delete a single manuscript block."""
        stmt = delete(assets).where(
            and_(
                assets.c.asset_id == block_id,
                assets.c.project_id == project_id,
                _block_type_clause(),
            )
        )
        with self.connect() as conn:
            result = conn.execute(stmt)
            return result.rowcount or 0

    # ------------------------------------------------------------------
    # Reorder
    # ------------------------------------------------------------------

    def reorder_blocks(
        self, project_id: str, block_ids: list[str]
    ) -> None:
        """Reassign block_order in the given order (gap=10).

        Uses ``json_set`` on ``payload_json`` to update the embedded order.
        """
        now = _now()
        with self.connect() as conn:
            for idx, bid in enumerate(block_ids):
                new_order = (idx + 1) * _BLOCK_ORDER_GAP
                conn.execute(
                    text(
                        "UPDATE assets "
                        "SET payload_json = json_set(COALESCE(payload_json, '{}'), '$.block_order', :order), "
                        "    updated_at = :now "
                        "WHERE asset_id = :bid AND project_id = :pid "
                        "  AND asset_type = 'manuscript_block'"
                    ),
                    {"order": new_order, "now": now, "bid": bid, "pid": project_id},
                )

    # ------------------------------------------------------------------
    # Tag
    # ------------------------------------------------------------------

    def tag_blocks(
        self, project_id: str, block_ids: list[str], chapter_tag: str
    ) -> int:
        """Update ``chapter_tag`` in payload_json for the given block IDs."""
        now = _now()
        count = 0
        with self.connect() as conn:
            for bid in block_ids:
                row = conn.execute(
                    select(assets.c.payload_json).where(
                        and_(
                            assets.c.asset_id == bid,
                            assets.c.project_id == project_id,
                            _block_type_clause(),
                        )
                    )
                ).fetchone()
                if row is None:
                    continue
                try:
                    payload = json.loads(row[0] or "{}")
                except (json.JSONDecodeError, TypeError):
                    payload = {}
                payload["chapter_tag"] = chapter_tag
                conn.execute(
                    update(assets)
                    .where(
                        and_(
                            assets.c.asset_id == bid,
                            assets.c.project_id == project_id,
                            _block_type_clause(),
                        )
                    )
                    .values(
                        payload_json=json.dumps(payload, ensure_ascii=False),
                        updated_at=now,
                    )
                )
                count += 1
        return count

    # ------------------------------------------------------------------
    # Continuation context
    # ------------------------------------------------------------------

    def get_continuation_blocks(
        self, project_id: str, *, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Return the last *limit* blocks ordered by block_order DESC.

        Used to build continuation context for the writer agent.
        """
        stmt = (
            select(assets)
            .where(
                and_(
                    assets.c.project_id == project_id,
                    _block_type_clause(),
                )
            )
            .order_by(_block_order_expr().desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(row._mapping) for row in conn.execute(stmt).fetchall()]
