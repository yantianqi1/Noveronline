"""Repository for SaaS-style writer runs, events, drafts, and adoptions."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, and_, func, insert, select, update

from app.tables.writer_runs import (
    writer_draft_events,
    writer_drafts,
    writer_run_events,
    writer_runs,
)

from .base import BaseRepository
from .manuscript_repo import ManuscriptRepository


LOCAL_TENANT_ID = "local_tenant"
LOCAL_USER_ID = "local_user"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(data: Any) -> str:
    return json.dumps(data if data is not None else {}, ensure_ascii=False)


def _load_json(raw: str | None) -> Any:
    try:
        return json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}


class WriterRunRepository(BaseRepository):
    def __init__(self, engine: Engine):
        super().__init__(engine)

    def create_run(
        self,
        *,
        tenant_id: str,
        project_id: str,
        started_by: str | None,
        mode: str,
        instruction: str,
        module_key: str,
        chapter_id: str | None = None,
        scene_id: str | None = None,
        options: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        timestamp = _now()
        values = {
            "run_id": run_id or f"run_{uuid.uuid4().hex}",
            "tenant_id": tenant_id,
            "project_id": project_id,
            "status": "pending",
            "mode": mode or "draft",
            "chapter_id": chapter_id,
            "scene_id": scene_id,
            "instruction": instruction or "",
            "module_key": module_key or "writer_composer",
            "requested_by": started_by,
            "options_json": _json(options or {}),
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        with self.connect() as conn:
            conn.execute(insert(writer_runs).values(**values))
        row = self.get_run(tenant_id, values["run_id"])
        if row is None:
            raise RuntimeError("writer run was not persisted")
        return row

    def get_run(self, tenant_id: str, run_id: str) -> dict[str, Any] | None:
        stmt = (
            select(writer_runs)
            .where(
                and_(
                    writer_runs.c.tenant_id == tenant_id,
                    writer_runs.c.run_id == run_id,
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            return self._serialize_run(conn.execute(stmt).fetchone())

    def mark_running(self, tenant_id: str, run_id: str) -> None:
        self._update_run(tenant_id, run_id, status="running")

    def mark_completed(
        self,
        tenant_id: str,
        run_id: str,
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        self._update_run(
            tenant_id,
            run_id,
            status="completed",
            result_json=_json(result or {}),
            completed_at=_now(),
        )

    def mark_failed(
        self,
        tenant_id: str,
        run_id: str,
        *,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self._update_run(
            tenant_id,
            run_id,
            status="failed",
            error_code=code,
            error_message=message,
            result_json=_json({"details": details or {}}),
            completed_at=_now(),
        )

    def mark_cancelled(self, tenant_id: str, run_id: str) -> None:
        self._update_run(tenant_id, run_id, status="cancelled", completed_at=_now())

    def append_event(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        timestamp = _now()
        with self.connect() as conn:
            max_order = conn.execute(
                select(func.max(writer_run_events.c.event_order)).where(
                    and_(
                        writer_run_events.c.tenant_id == tenant_id,
                        writer_run_events.c.run_id == run_id,
                    )
                )
            ).scalar()
            values = {
                "event_id": f"evt_{uuid.uuid4().hex}",
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "event_order": int(max_order or 0) + 1,
                "event_type": event_type,
                "payload_json": _json(payload or {}),
                "created_at": timestamp,
            }
            conn.execute(insert(writer_run_events).values(**values))
        event = self.list_events(tenant_id, run_id)[-1]
        return event

    def list_events(self, tenant_id: str, run_id: str) -> list[dict[str, Any]]:
        stmt = (
            select(writer_run_events)
            .where(
                and_(
                    writer_run_events.c.tenant_id == tenant_id,
                    writer_run_events.c.run_id == run_id,
                )
            )
            .order_by(writer_run_events.c.event_order.asc())
        )
        with self.connect() as conn:
            return [self._serialize_event(row) for row in conn.execute(stmt).fetchall()]

    def save_draft_revision(
        self,
        *,
        tenant_id: str,
        project_id: str,
        run_id: str,
        chapter_id: str | None,
        scene_id: str | None,
        content: str,
        metadata: dict[str, Any] | None,
        created_by: str | None,
    ) -> dict[str, Any]:
        timestamp = _now()
        with self.connect() as conn:
            existing = conn.execute(
                select(writer_drafts).where(
                    and_(
                        writer_drafts.c.tenant_id == tenant_id,
                        writer_drafts.c.run_id == run_id,
                    )
                )
            ).fetchone()
            values = {
                "tenant_id": tenant_id,
                "project_id": project_id,
                "run_id": run_id,
                "chapter_id": chapter_id,
                "scene_id": scene_id,
                "status": "draft",
                "content": content,
                "metadata_json": _json(metadata or {}),
                "created_by": created_by,
                "updated_at": timestamp,
            }
            if existing is None:
                draft_id = f"draft_{uuid.uuid4().hex}"
                conn.execute(
                    insert(writer_drafts).values(
                        draft_id=draft_id,
                        created_at=timestamp,
                        **values,
                    )
                )
                self._insert_draft_event(
                    conn,
                    tenant_id=tenant_id,
                    draft_id=draft_id,
                    event_type="draft.saved",
                    payload={"run_id": run_id},
                    created_at=timestamp,
                )
            else:
                draft_id = existing._mapping["draft_id"]
                conn.execute(
                    update(writer_drafts)
                    .where(writer_drafts.c.draft_id == draft_id)
                    .values(**values)
                )
        draft = self.get_draft(tenant_id, draft_id)
        if draft is None:
            raise RuntimeError("draft was not persisted")
        return draft

    def get_draft(self, tenant_id: str, draft_id: str) -> dict[str, Any] | None:
        stmt = (
            select(writer_drafts)
            .where(
                and_(
                    writer_drafts.c.tenant_id == tenant_id,
                    writer_drafts.c.draft_id == draft_id,
                )
            )
            .limit(1)
        )
        with self.connect() as conn:
            return self._serialize_draft(conn.execute(stmt).fetchone())

    def list_drafts_for_run(self, tenant_id: str, run_id: str) -> list[dict[str, Any]]:
        stmt = select(writer_drafts).where(
            and_(
                writer_drafts.c.tenant_id == tenant_id,
                writer_drafts.c.run_id == run_id,
            )
        )
        with self.connect() as conn:
            return [self._serialize_draft(row) for row in conn.execute(stmt).fetchall()]

    def adopt_draft_to_manuscript(
        self,
        *,
        tenant_id: str,
        draft_id: str,
        adopted_by: str | None,
    ) -> dict[str, Any]:
        draft = self.get_draft(tenant_id, draft_id)
        if draft is None:
            raise ValueError(f"draft not found: {draft_id}")
        if not (draft.get("content") or "").strip():
            raise ValueError("draft content is empty")
        if draft.get("adopted_block_id"):
            return {
                "draft_id": draft_id,
                "block_id": draft["adopted_block_id"],
                "already_adopted": True,
            }

        block_id = f"ms_{uuid.uuid4().hex}"
        timestamp = _now()
        payload = {
            "chapter_id": draft.get("chapter_id"),
            "source_scene_id": draft.get("scene_id"),
            "source_draft_id": draft_id,
            "run_id": draft.get("run_id"),
            "block_order": self._next_block_order(draft["project_id"]),
        }
        ManuscriptRepository(self.engine).commit_block(
            draft["project_id"],
            {
                "asset_id": block_id,
                "title": "Writer draft adoption",
                "summary": "",
                "content": draft["content"],
                "payload_json": _json(payload),
                "tags_json": "[]",
                "source_kind": "writer_draft",
                "source_ref": draft_id,
                "enabled": 1,
                "pinned": 0,
                "word_count": len(draft["content"]),
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )
        with self.connect() as conn:
            conn.execute(
                update(writer_drafts)
                .where(writer_drafts.c.draft_id == draft_id)
                .values(
                    status="adopted",
                    adopted_block_id=block_id,
                    updated_at=timestamp,
                )
            )
            self._insert_draft_event(
                conn,
                tenant_id=tenant_id,
                draft_id=draft_id,
                event_type="draft.adopted",
                payload={"block_id": block_id, "adopted_by": adopted_by},
                created_at=timestamp,
            )
        return {"draft_id": draft_id, "block_id": block_id, "already_adopted": False}

    def _update_run(self, tenant_id: str, run_id: str, **values: Any) -> None:
        values["updated_at"] = _now()
        with self.connect() as conn:
            conn.execute(
                update(writer_runs)
                .where(
                    and_(
                        writer_runs.c.tenant_id == tenant_id,
                        writer_runs.c.run_id == run_id,
                    )
                )
                .values(**values)
            )

    def _next_block_order(self, project_id: str) -> int:
        blocks = ManuscriptRepository(self.engine).list_blocks(project_id, include_content=False)
        max_order = 0
        for block in blocks:
            payload = _load_json(block.get("payload_json"))
            try:
                max_order = max(max_order, int(payload.get("block_order") or 0))
            except (TypeError, ValueError):
                continue
        return max_order + 10

    @staticmethod
    def _insert_draft_event(conn, *, tenant_id: str, draft_id: str, event_type: str, payload: dict[str, Any], created_at: str) -> None:
        conn.execute(
            insert(writer_draft_events).values(
                event_id=f"de_{uuid.uuid4().hex}",
                tenant_id=tenant_id,
                draft_id=draft_id,
                event_type=event_type,
                payload_json=_json(payload),
                created_at=created_at,
            )
        )

    @staticmethod
    def _serialize_run(row) -> dict[str, Any] | None:
        data = BaseRepository.row_to_dict(row)
        if data is None:
            return None
        data["options"] = _load_json(data.pop("options_json", None))
        data["result"] = _load_json(data.pop("result_json", None)) if data.get("result_json") else None
        return data

    @staticmethod
    def _serialize_event(row) -> dict[str, Any]:
        data = dict(row._mapping)
        data["type"] = data.pop("event_type")
        data["payload"] = _load_json(data.pop("payload_json", None))
        return data

    @staticmethod
    def _serialize_draft(row) -> dict[str, Any] | None:
        data = BaseRepository.row_to_dict(row)
        if data is None:
            return None
        data["metadata"] = _load_json(data.pop("metadata_json", None))
        return data
