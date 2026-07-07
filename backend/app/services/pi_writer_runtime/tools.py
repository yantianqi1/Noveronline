"""Read-only writer tools for the Writer-first runtime bridge."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine

from app.database import get_engine
from app.repositories.asset_repo import AssetRepository
from app.repositories.entity_repo import EntityRepository
from app.repositories.graph_repo import GraphRepository
from app.repositories.world_rule_repo import WorldRuleRepository
from app.repositories.worldline_session_repo import WorldlineSessionRepository

from .errors import ToolPermissionDeniedError


READ_TOOLS = {
    "query_assets",
    "query_world_rules",
    "query_character_profile",
    "query_graph_neighbors",
    "query_worldline_paths",
}


class WriterToolRegistry:
    """Execute writer context tools against the unified database."""

    def __init__(self, engine: Engine | None = None):
        self.engine = engine or get_engine()

    def execute(
        self,
        tool_name: str,
        context: dict[str, str],
        args: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if tool_name not in READ_TOOLS:
            raise ToolPermissionDeniedError(f"tool is not allowed: {tool_name}")
        payload = args or {}
        self._validate_context(context, payload)
        project_id = context["project_id"]
        if tool_name == "query_assets":
            return self._query_assets(project_id, payload)
        if tool_name == "query_world_rules":
            return self._query_world_rules(project_id, payload)
        if tool_name == "query_character_profile":
            return self._query_character_profile(project_id, payload)
        if tool_name == "query_graph_neighbors":
            return self._query_graph_neighbors(project_id, payload)
        if tool_name == "query_worldline_paths":
            return self._query_worldline_paths(project_id, payload)
        raise ToolPermissionDeniedError(f"tool is not allowed: {tool_name}")

    @staticmethod
    def _validate_context(context: dict[str, str], args: dict[str, Any]) -> None:
        for key in ("tenant_id", "project_id", "run_id"):
            if not context.get(key):
                raise ToolPermissionDeniedError(f"missing runtime {key}")
            if args.get(key) and args[key] != context[key]:
                raise ToolPermissionDeniedError(f"tool {key} does not match runtime context")

    def _query_assets(self, project_id: str, args: dict[str, Any]) -> dict[str, Any]:
        repo = AssetRepository(self.engine)
        selected_ids = [str(item) for item in args.get("selected_asset_ids") or [] if str(item)]
        items: list[dict[str, Any]] = []
        for asset_id in selected_ids:
            row = repo.get_asset(asset_id)
            if row and (row.get("project_id") in (None, project_id)):
                items.append(_asset_payload(row))
        if not selected_ids:
            query = str(args.get("query") or "").strip()
            if query:
                rows = repo.search_assets(
                    query,
                    project_id=project_id,
                    asset_type=args.get("asset_type"),
                    enabled_only=True,
                    limit=int(args.get("limit") or 8),
                )
            else:
                rows = repo.list_assets(
                    project_id=project_id,
                    asset_type=args.get("asset_type"),
                    enabled_only=True,
                    limit=int(args.get("limit") or 8),
                )
            items = [_asset_payload(row) for row in rows]
        return {"tool": "query_assets", "items": items}

    def _query_world_rules(self, project_id: str, args: dict[str, Any]) -> dict[str, Any]:
        query = str(args.get("query") or "").strip()
        rows = WorldRuleRepository(self.engine).list_rules(project_id, limit=int(args.get("limit") or 30))
        if query:
            rows = [
                row
                for row in rows
                if query in (row.get("fact_text") or "")
                or query in (row.get("evidence_snippet") or "")
            ]
        items = [
            {
                "evidence_id": row.get("evidence_id"),
                "fact_text": row.get("fact_text") or "",
                "chapter_order": row.get("chapter_order"),
                "evidence_snippet": row.get("evidence_snippet") or "",
            }
            for row in rows[: int(args.get("limit") or 8)]
        ]
        return {"tool": "query_world_rules", "items": items}

    def _query_character_profile(self, project_id: str, args: dict[str, Any]) -> dict[str, Any]:
        repo = EntityRepository(self.engine)
        entity = None
        entity_id = str(args.get("entity_id") or "").strip()
        if entity_id:
            entity = repo.get_entity(project_id, entity_id)
        if entity is None:
            name = str(args.get("name") or "").strip()
            if name:
                entity = repo.get_entity_by_name(project_id, name)
        return {
            "tool": "query_character_profile",
            "entity": _entity_payload(entity) if entity else None,
        }

    def _query_graph_neighbors(self, project_id: str, args: dict[str, Any]) -> dict[str, Any]:
        repo = GraphRepository(self.engine)
        node_uuid = str(args.get("node_uuid") or "").strip()
        node = repo.load_node(project_id, node_uuid) if node_uuid else None
        if node is None:
            node_name = str(args.get("node_name") or "").strip()
            resolved = repo.lookup_node_by_name_or_alias(project_id, node_name) if node_name else None
            if resolved:
                node_uuid = resolved["uuid"]
                node = repo.load_node(project_id, node_uuid)
        neighbors = repo.get_neighbors_with_labels(project_id, node_uuid, limit=int(args.get("limit") or 8)) if node_uuid else []
        return {
            "tool": "query_graph_neighbors",
            "node": node,
            "neighbors": neighbors,
        }

    def _query_worldline_paths(self, project_id: str, args: dict[str, Any]) -> dict[str, Any]:
        requested_ids = {str(item) for item in args.get("path_ids") or [] if str(item)}
        sessions = WorldlineSessionRepository(self.engine).list_sessions(project_id=project_id, limit=100)
        items: list[dict[str, Any]] = []
        for session in sessions:
            payload = WorldlineSessionRepository(self.engine).load_session(session["session_id"]) or {}
            for path in _extract_saved_paths(payload):
                path_id = str(path.get("path_id") or path.get("id") or "")
                if requested_ids and path_id not in requested_ids:
                    continue
                items.append(
                    {
                        "path_id": path_id,
                        "session_id": session["session_id"],
                        "title": path.get("title") or "",
                        "summary": path.get("summary") or "",
                        "selected_event_ids": list(path.get("selected_event_ids") or []),
                        "writer_instruction": path.get("writer_instruction") or "",
                        "lifecycle": path.get("lifecycle") or "simulation",
                    }
                )
        return {"tool": "query_worldline_paths", "items": items[: int(args.get("limit") or 8)]}


def _asset_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "asset_id": row.get("asset_id"),
        "project_id": row.get("project_id"),
        "asset_type": row.get("asset_type"),
        "category": row.get("category"),
        "title": row.get("title"),
        "summary": row.get("summary"),
        "content": row.get("content"),
        "tags": _load_json(row.get("tags_json"), []),
        "payload": _load_json(row.get("payload_json"), {}),
        "source": {"kind": row.get("source_kind") or "", "ref": row.get("source_ref") or ""},
    }


def _entity_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": row.get("entity_id"),
        "name": row.get("name"),
        "entity_type": row.get("entity_type"),
        "importance_tier": row.get("importance_tier"),
        "summary": row.get("summary") or "",
        "core_drive": row.get("core_drive") or "",
        "surface_mask": row.get("surface_mask") or "",
        "hidden_tension": row.get("hidden_tension") or "",
        "speech_style": row.get("speech_style") or "",
        "agent_behavior_hint": row.get("agent_behavior_hint") or "",
        "profile": _load_json(row.get("profile_json"), {}),
    }


def _extract_saved_paths(session_payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("saved_paths", "savedPaths", "worldline_saved_paths"):
        value = session_payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _load_json(raw: str | None, fallback: Any) -> Any:
    try:
        return json.loads(raw or "")
    except (json.JSONDecodeError, TypeError):
        return fallback
