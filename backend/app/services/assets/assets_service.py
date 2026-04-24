"""资产库业务服务。

封装统一资产仓库的 CRUD、过滤、搜索、批量启停、批量分类。
所有 ``search_*`` 默认只返回 ``enabled=1`` 的资产，便于 agent 工具直接调用。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Iterable

from ...database import get_engine
from ...repositories.asset_repo import AssetRepository

GLOBAL_SCOPE = "global"
PROJECT_SCOPE = "project"


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _new_id() -> str:
    return f"asset_{uuid.uuid4().hex[:16]}"


def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
    d = dict(row)
    for k in ("payload_json", "tags_json"):
        raw = d.get(k)
        if isinstance(raw, str) and raw:
            try:
                d[k.removesuffix("_json")] = json.loads(raw)
            except json.JSONDecodeError:
                d[k.removesuffix("_json")] = raw
        else:
            d[k.removesuffix("_json")] = [] if k == "tags_json" else {}
    d["enabled"] = bool(d.get("enabled"))
    d["pinned"] = bool(d.get("pinned"))
    return d


# ----------------------------------------------------------------------
# Service
# ----------------------------------------------------------------------


class AssetsService:
    """双层资产库的业务入口。"""

    def __init__(self, repo: AssetRepository | None = None) -> None:
        self._repo = repo or AssetRepository(get_engine())

    # -- create / update / delete --------------------------------------

    def create(
        self,
        *,
        scope: str,
        asset_type: str,
        title: str,
        project_id: str | None = None,
        category: str = "",
        summary: str = "",
        content: str = "",
        payload: dict | None = None,
        tags: list[str] | None = None,
        source_kind: str = "manual",
        source_ref: str = "",
        enabled: bool = True,
        pinned: bool = False,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        if not title.strip():
            raise ValueError("title is required")
        if scope == PROJECT_SCOPE and not project_id:
            raise ValueError("project scope requires project_id")
        now = _now()
        aid = asset_id or _new_id()
        word_count = len(content or "")
        self._repo.create_asset({
            "asset_id": aid,
            "scope": scope,
            "project_id": project_id if scope == PROJECT_SCOPE else None,
            "asset_type": asset_type,
            "category": category or "",
            "title": title,
            "summary": summary or "",
            "content": content or "",
            "payload_json": json.dumps(payload or {}, ensure_ascii=False),
            "tags_json": json.dumps(tags or [], ensure_ascii=False),
            "source_kind": source_kind or "",
            "source_ref": source_ref or "",
            "enabled": 1 if enabled else 0,
            "pinned": 1 if pinned else 0,
            "word_count": word_count,
            "created_at": now,
            "updated_at": now,
        })
        return self.get(aid, scope=scope, project_id=project_id) or {}

    def update(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        allowed = {
            "asset_type", "category", "title", "summary", "content",
            "source_kind", "source_ref",
        }
        update_vals: dict[str, Any] = {}
        for key, value in fields.items():
            if key in allowed:
                update_vals[key] = value if value is not None else ""
            elif key == "payload":
                update_vals["payload_json"] = json.dumps(value or {}, ensure_ascii=False)
            elif key == "tags":
                update_vals["tags_json"] = json.dumps(value or [], ensure_ascii=False)
            elif key == "enabled":
                update_vals["enabled"] = 1 if value else 0
            elif key == "pinned":
                update_vals["pinned"] = 1 if value else 0
        if "content" in fields:
            update_vals["word_count"] = len(fields.get("content") or "")
        if not update_vals:
            return self.get(asset_id, scope=scope, project_id=project_id) or {}
        update_vals["updated_at"] = _now()
        self._repo.update_asset(asset_id, **update_vals)
        return self.get(asset_id, scope=scope, project_id=project_id) or {}

    def delete(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> bool:
        return self._repo.delete_asset(asset_id) > 0

    # -- read ----------------------------------------------------------

    def get(
        self,
        asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> dict[str, Any] | None:
        row = self._repo.get_asset(asset_id)
        return _row_to_dict(row) if row else None

    def find(self, asset_id: str, project_id: str | None = None) -> dict[str, Any] | None:
        """Look up an asset across both layers (project first, then global)."""
        if project_id:
            row = self.get(asset_id, scope=PROJECT_SCOPE, project_id=project_id)
            if row:
                return row
        return self.get(asset_id, scope=GLOBAL_SCOPE)

    def list(
        self,
        *,
        scope: str,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = False,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        rows = self._repo.list_assets(
            scope=scope,
            project_id=project_id,
            asset_type=asset_type,
            category=category,
            enabled_only=enabled_only,
            limit=limit,
            offset=offset,
        )
        return [_row_to_dict(r) for r in rows]

    def search(
        self,
        query: str,
        *,
        scope: str,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search within a single layer using LIKE."""
        rows = self._repo.search_assets(
            query,
            scope=scope,
            project_id=project_id,
            asset_type=asset_type,
            category=category,
            enabled_only=enabled_only,
            limit=limit,
        )
        results = []
        for r in rows:
            d = _row_to_dict(r)
            d["snippet"] = (r.get("content") or "")[:96]
            results.append(d)
        return results

    def search_merged(
        self,
        query: str,
        *,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = True,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search project layer + global layer, merged. Project hits come first."""
        merged: list[dict[str, Any]] = []
        if project_id:
            merged.extend(
                self.search(
                    query,
                    scope=PROJECT_SCOPE,
                    project_id=project_id,
                    asset_type=asset_type,
                    category=category,
                    enabled_only=enabled_only,
                    limit=limit,
                )
            )
        merged.extend(
            self.search(
                query,
                scope=GLOBAL_SCOPE,
                asset_type=asset_type,
                category=category,
                enabled_only=enabled_only,
                limit=limit,
            )
        )
        return merged[:limit]

    def list_merged(
        self,
        *,
        project_id: str | None = None,
        asset_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = False,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        if project_id:
            merged.extend(
                self.list(
                    scope=PROJECT_SCOPE,
                    project_id=project_id,
                    asset_type=asset_type,
                    category=category,
                    enabled_only=enabled_only,
                    limit=limit,
                )
            )
        merged.extend(
            self.list(
                scope=GLOBAL_SCOPE,
                asset_type=asset_type,
                category=category,
                enabled_only=enabled_only,
                limit=limit,
            )
        )
        return merged

    # -- batch ops -----------------------------------------------------

    def batch_set_enabled(
        self,
        asset_ids: Iterable[str],
        enabled: bool,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> int:
        ids = list(asset_ids)
        if not ids:
            return 0
        return self._repo.batch_set_enabled(ids, enabled, updated_at=_now())

    def batch_set_category(
        self,
        asset_ids: Iterable[str],
        category: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> int:
        ids = list(asset_ids)
        if not ids:
            return 0
        return self._repo.batch_set_category(ids, category, updated_at=_now())

    # -- links ---------------------------------------------------------

    def link(
        self,
        src_asset_id: str,
        dst_asset_id: str,
        relation: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> None:
        self._repo.upsert_link({
            "src_asset_id": src_asset_id,
            "dst_asset_id": dst_asset_id,
            "relation": relation,
            "project_id": project_id if scope == PROJECT_SCOPE else None,
            "created_at": _now(),
        })

    def list_links(
        self,
        src_asset_id: str,
        *,
        scope: str,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self._repo.list_links(src_asset_id)
