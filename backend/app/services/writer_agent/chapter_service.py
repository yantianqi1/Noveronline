"""Chapter CRUD service layer."""
from __future__ import annotations

import logging
import uuid

from app.database import get_engine
from app.repositories.chapter_repo import ChapterRepository
from app.repositories.outline_repo import OutlineRepository


logger = logging.getLogger(__name__)


class ChapterService:
    def __init__(self):
        engine = get_engine()
        self._chapters = ChapterRepository(engine)
        self._outlines = OutlineRepository(engine)
        self._plan_service = None

    def _get_plan_service(self):
        """Lazy-init BookPlanService to avoid circular-import at module load."""
        if self._plan_service is None:
            from app.services.writer_agent.book_plan_service import BookPlanService
            self._plan_service = BookPlanService()
        return self._plan_service

    def list_chapters(self, project_id: str) -> list:
        return self._chapters.list_chapters(project_id)

    def create_chapter(
        self,
        project_id: str,
        title: str,
        chapter_order: int = None,
        *,
        _skip_plan_sync: bool = False,
    ) -> dict:
        chapter_id = f"ch_{uuid.uuid4().hex[:12]}"
        if chapter_order is None:
            chapters = self._chapters.list_chapters(project_id)
            chapter_order = max((c["chapter_order"] for c in chapters), default=0) + 1
        self._chapters.create_chapter(project_id, chapter_id, chapter_order, title)
        if not _skip_plan_sync:
            self._sync_active_plan_append(project_id, chapter_id)
        return {"chapter_id": chapter_id, "chapter_order": chapter_order, "title": title}

    def update_chapter(self, project_id: str, chapter_id: str, **kwargs) -> dict:
        # Snapshot old outline before overwriting
        outline_label = kwargs.pop("outline_label", "")
        if "outline_json" in kwargs:
            ch = self._chapters.get_chapter(project_id, chapter_id)
            old_outline = (ch or {}).get("outline_json", "[]")
            if old_outline and (old_outline != "[]" or outline_label):
                self._outlines.save_outline_version(project_id, chapter_id, old_outline, label=outline_label)
        self._chapters.update_chapter(project_id, chapter_id, **kwargs)
        return {"chapter_id": chapter_id, "updated": True}

    def delete_chapter(self, project_id: str, chapter_id: str, *, _skip_plan_sync: bool = False):
        self._chapters.delete_chapter(project_id, chapter_id)
        if not _skip_plan_sync:
            self._sync_all_plans_remove(project_id, chapter_id)

    def list_outline_versions(self, project_id: str, chapter_id: str) -> list:
        return self._outlines.list_outline_versions(project_id, chapter_id)

    def restore_outline_version(self, project_id: str, chapter_id: str, version_id: str) -> dict:
        target = self._outlines.get_outline_version(project_id, version_id)
        if not target:
            raise ValueError(f"Version {version_id} not found")
        # Snapshot current value before restoring
        ch = self._chapters.get_chapter(project_id, chapter_id)
        current_outline = (ch or {}).get("outline_json", "[]")
        if current_outline and current_outline != "[]":
            self._outlines.save_outline_version(project_id, chapter_id, current_outline, label="回退前快照")
        self._chapters.update_chapter(project_id, chapter_id, outline_json=target["outline_json"])
        return {"chapter_id": chapter_id, "restored_version_id": version_id}

    # ------------------------------------------------------------------
    # book_plan sync (best-effort; errors are logged, never raised)
    # ------------------------------------------------------------------

    def _sync_active_plan_append(self, project_id: str, chapter_id: str) -> None:
        try:
            plan = self._get_plan_service().get_active_plan(project_id)
            if not plan:
                return
            self._get_plan_service().append_chapter_id(plan["plan_id"], chapter_id)
        except Exception:
            logger.exception("sync active book_plan append failed: project=%s chapter=%s", project_id, chapter_id)

    def _sync_all_plans_remove(self, project_id: str, chapter_id: str) -> None:
        try:
            svc = self._get_plan_service()
            for plan in svc.list_plans(project_id):
                if chapter_id in (plan.get("chapter_ids") or []):
                    svc.remove_chapter_id(plan["plan_id"], chapter_id)
        except Exception:
            logger.exception("sync book_plan remove failed: project=%s chapter=%s", project_id, chapter_id)
