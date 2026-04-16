"""Book plan repository (multi-chapter agent run plan)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, delete, insert, select, update

from app.tables.novel import book_plans

from .base import ProjectScopedRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_CREATABLE_COLS = {
    "title",
    "chapter_count",
    "per_chapter_word_target",
    "word_tolerance_pct",
    "overall_direction",
    "global_brief",
    "start_chapter_order",
    "forbidden_lexicon_asset_ids",
    "style_asset_ids",
    "preset_id",
}

_UPDATABLE_COLS = _CREATABLE_COLS | {
    "status",
    "current_chapter_order",
    "last_stage",
    "outline_version_ids",
    "chapter_ids",
    "error_log",
    "retrieval_summary",
}


class BookPlanRepository(ProjectScopedRepository):
    """CRUD for book_plans."""

    def __init__(self, engine: Engine):
        super().__init__(engine, book_plans)

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_plans(self, project_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        stmt = (
            select(book_plans)
            .where(book_plans.c.project_id == project_id)
            .order_by(book_plans.c.created_at.desc())
            .limit(limit)
        )
        with self.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt).fetchall()]

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        stmt = select(book_plans).where(book_plans.c.plan_id == plan_id).limit(1)
        with self.connect() as conn:
            return self.row_to_dict(conn.execute(stmt).fetchone())

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_plan(self, project_id: str, **values: Any) -> dict[str, Any]:
        plan_id = f"bp_{uuid.uuid4().hex[:12]}"
        now = _now()
        payload = {k: v for k, v in values.items() if k in _CREATABLE_COLS}
        row = {
            "plan_id": plan_id,
            "project_id": project_id,
            "status": "draft",
            "current_chapter_order": 0,
            "last_stage": "",
            "outline_version_ids": "[]",
            "chapter_ids": "[]",
            "error_log": "[]",
            "retrieval_summary": "",
            "created_at": now,
            "updated_at": now,
            **payload,
        }
        with self.connect() as conn:
            conn.execute(insert(book_plans).values(**row))
        return row

    def update_plan(self, plan_id: str, **kwargs: Any) -> bool:
        updates = {k: v for k, v in kwargs.items() if k in _UPDATABLE_COLS}
        if not updates:
            return False
        updates["updated_at"] = _now()
        stmt = update(book_plans).where(book_plans.c.plan_id == plan_id).values(**updates)
        with self.connect() as conn:
            result = conn.execute(stmt)
            return (result.rowcount or 0) > 0

    def delete_plan(self, plan_id: str) -> int:
        stmt = delete(book_plans).where(book_plans.c.plan_id == plan_id)
        with self.connect() as conn:
            result = conn.execute(stmt)
            return result.rowcount or 0
