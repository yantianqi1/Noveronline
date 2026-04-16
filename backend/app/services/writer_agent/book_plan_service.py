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
