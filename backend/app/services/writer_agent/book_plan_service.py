"""Book plan service layer — multi-chapter agent run plans."""

from __future__ import annotations

import json
from typing import Any, Iterable

from app.database import get_engine
from app.repositories.book_plan_repo import BookPlanRepository


_LIST_FIELDS = {
    "forbidden_lexicon_asset_ids",
    "style_asset_ids",
    "outline_version_ids",
    "chapter_ids",
    "error_log",
}


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _hydrate(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    for field in _LIST_FIELDS:
        out[field] = _loads(out.get(field), [])
    return out


class BookPlanService:
    def __init__(self) -> None:
        self._repo = BookPlanRepository(get_engine())

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_plans(self, project_id: str) -> list[dict[str, Any]]:
        return [_hydrate(r) for r in self._repo.list_plans(project_id) if r]

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return _hydrate(self._repo.get_plan(plan_id))

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_plan(
        self,
        project_id: str,
        *,
        title: str,
        chapter_count: int,
        per_chapter_word_target: int,
        word_tolerance_pct: int = 10,
        overall_direction: str = "",
        global_brief: str = "",
        start_chapter_order: int = 1,
        forbidden_lexicon_asset_ids: Iterable[str] | None = None,
        style_asset_ids: Iterable[str] | None = None,
        preset_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "title": title,
            "chapter_count": int(chapter_count),
            "per_chapter_word_target": int(per_chapter_word_target),
            "word_tolerance_pct": int(word_tolerance_pct),
            "overall_direction": overall_direction,
            "global_brief": global_brief,
            "start_chapter_order": int(start_chapter_order),
            "forbidden_lexicon_asset_ids": _dumps(list(forbidden_lexicon_asset_ids or [])),
            "style_asset_ids": _dumps(list(style_asset_ids or [])),
            "preset_id": preset_id,
        }
        row = self._repo.create_plan(project_id, **payload)
        return _hydrate(row)

    def update_plan(self, plan_id: str, **kwargs: Any) -> dict[str, Any] | None:
        updates = dict(kwargs)
        for field in _LIST_FIELDS & updates.keys():
            updates[field] = _dumps(updates[field])
        self._repo.update_plan(plan_id, **updates)
        return self.get_plan(plan_id)

    def set_status(
        self,
        plan_id: str,
        status: str,
        *,
        last_stage: str | None = None,
        current_chapter_order: int | None = None,
    ) -> None:
        updates: dict[str, Any] = {"status": status}
        if last_stage is not None:
            updates["last_stage"] = last_stage
        if current_chapter_order is not None:
            updates["current_chapter_order"] = int(current_chapter_order)
        self._repo.update_plan(plan_id, **updates)

    def append_outline_version(self, plan_id: str, version_id: str) -> None:
        plan = self.get_plan(plan_id)
        if not plan:
            return
        ids = list(plan.get("outline_version_ids") or [])
        ids.append(version_id)
        self._repo.update_plan(plan_id, outline_version_ids=_dumps(ids))

    def append_chapter_id(self, plan_id: str, chapter_id: str) -> None:
        plan = self.get_plan(plan_id)
        if not plan:
            return
        ids = list(plan.get("chapter_ids") or [])
        if chapter_id not in ids:
            ids.append(chapter_id)
        self._repo.update_plan(plan_id, chapter_ids=_dumps(ids))

    def remove_chapter_id(self, plan_id: str, chapter_id: str) -> None:
        plan = self.get_plan(plan_id)
        if not plan:
            return
        ids = list(plan.get("chapter_ids") or [])
        if chapter_id not in ids:
            return
        ids = [cid for cid in ids if cid != chapter_id]
        self._repo.update_plan(plan_id, chapter_ids=_dumps(ids))

    def get_active_plan(self, project_id: str) -> dict[str, Any] | None:
        """Return the most recently updated active plan for the project.

        Active = status IN ('draft','retrieving','outlining','writing').
        Returns None when no active plan exists.
        """
        active_statuses = {"draft", "retrieving", "outlining", "writing"}
        plans = self.list_plans(project_id)
        active = [p for p in plans if (p or {}).get("status") in active_statuses]
        if not active:
            return None
        active.sort(key=lambda p: p.get("updated_at") or "", reverse=True)
        return active[0]

    def append_error(self, plan_id: str, error: dict[str, Any]) -> None:
        plan = self.get_plan(plan_id)
        if not plan:
            return
        log = list(plan.get("error_log") or [])
        log.append(error)
        self._repo.update_plan(plan_id, error_log=_dumps(log))

    def set_retrieval_summary(self, plan_id: str, summary: str) -> None:
        self._repo.update_plan(plan_id, retrieval_summary=summary)

    def delete_plan(self, plan_id: str) -> int:
        return self._repo.delete_plan(plan_id)

    # ------------------------------------------------------------------
    # Aggregate status (StatusBar data source)
    # ------------------------------------------------------------------

    def get_plan_status(self, plan_id: str) -> dict[str, Any] | None:
        """Aggregate plan progress for the writer StatusBar.

        Joins the plan row with its chapter_ids against ChapterRepository to
        produce per-chapter word counts, totals, and derived progress fields.
        """
        plan = self.get_plan(plan_id)
        if not plan:
            return None

        from app.repositories.chapter_repo import ChapterRepository

        chapter_repo = ChapterRepository(self._repo.engine)
        all_chapters = chapter_repo.list_chapters(plan["project_id"])
        by_id = {c["chapter_id"]: c for c in all_chapters}

        chapter_ids = list(plan.get("chapter_ids") or [])
        chapter_rows: list[dict[str, Any]] = []
        for cid in chapter_ids:
            ch = by_id.get(cid)
            if not ch:
                continue
            chapter_rows.append({
                "chapter_id": ch["chapter_id"],
                "chapter_order": ch.get("chapter_order") or 0,
                "title": ch.get("title") or "",
                "status": ch.get("status") or "draft",
                "word_count": int(ch.get("word_count") or 0),
            })
        chapter_rows.sort(key=lambda r: r["chapter_order"])

        per_target = int(plan.get("per_chapter_word_target") or 0)
        total_target = per_target * int(plan.get("chapter_count") or 0)
        total_written = sum(r["word_count"] for r in chapter_rows)
        progress_pct = (
            round(total_written / total_target * 100, 1)
            if total_target > 0
            else 0.0
        )

        completed = [r for r in chapter_rows if r["status"] == "completed"]
        in_progress = next(
            (r for r in chapter_rows if r["status"] not in ("completed", "draft")),
            None,
        )
        error_log = list(plan.get("error_log") or [])

        return {
            "plan_id": plan["plan_id"],
            "project_id": plan["project_id"],
            "title": plan.get("title") or "",
            "status": plan.get("status") or "draft",
            "last_stage": plan.get("last_stage") or "",
            "current_chapter_order": int(plan.get("current_chapter_order") or 0),
            "chapter_count": int(plan.get("chapter_count") or 0),
            "per_chapter_word_target": per_target,
            "total_word_target": total_target,
            "chapters": chapter_rows,
            "words_written_total": total_written,
            "progress_pct": progress_pct,
            "completed_chapter_count": len(completed),
            "in_progress_chapter_order": (
                in_progress["chapter_order"] if in_progress else None
            ),
            "error_count": len(error_log),
            "updated_at": plan.get("updated_at") or "",
        }
