"""Generate relationship bonds and plot threads for a subset of graph nodes.

Given a handful of user-selected story-graph nodes, call an LLM to draft:
  * bonds between them (persisted to the ``relationships`` table when both
    endpoints can be resolved to an entity)
  * plot threads that involve them (persisted to ``plot_threads`` and linked
    via ``thread_entity_links`` when at least one entity match is found)

Nodes whose names cannot be resolved to an entity are returned as
``unmapped_names`` so the frontend can surface a warning.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from ..repositories.entity_repo import EntityRepository
from ..repositories.graph_repo import GraphRepository
from ..repositories.relationship_repo import RelationshipRepository
from ..repositories.thread_repo import ThreadRepository
from ..utils.llm_json import normalize_json_object
from .llm_router import LlmRouter

logger = logging.getLogger(__name__)

MODULE_KEY = "graph_bond_generator"


@dataclass
class _ResolvedNode:
    uuid: str
    name: str
    labels: list[str]
    summary: str
    attributes: dict[str, Any]
    entity_id: str | None


class GraphBondGenerator:
    def __init__(
        self,
        engine: Engine,
        llm_router: LlmRouter,
    ) -> None:
        self._engine = engine
        self._llm_router = llm_router
        self._graph_repo = GraphRepository(engine)
        self._entity_repo = EntityRepository(engine)
        self._relationship_repo = RelationshipRepository(engine)
        self._thread_repo = ThreadRepository(engine)

    def run(
        self,
        project_id: str,
        node_uuids: list[str],
        *,
        generate_bonds: bool = True,
        generate_threads: bool = True,
    ) -> dict[str, Any]:
        if not (generate_bonds or generate_threads):
            raise ValueError("generate_bonds 与 generate_threads 至少选一个")

        resolved = self._load_selected_nodes(project_id, node_uuids)
        if len(resolved) < 2:
            raise ValueError("至少需要命中 2 个图谱节点")

        unmapped = [node.name for node in resolved if node.entity_id is None]

        raw = self._invoke_llm(resolved, generate_bonds, generate_threads)

        bonds_out: list[dict[str, Any]] = []
        threads_out: list[dict[str, Any]] = []

        if generate_bonds:
            bonds_out = self._persist_bonds(
                project_id, resolved, raw.get("bonds") or []
            )
        if generate_threads:
            threads_out = self._persist_threads(
                project_id, resolved, raw.get("plot_threads") or []
            )

        return {
            "bonds": bonds_out,
            "plot_threads": threads_out,
            "unmapped_names": unmapped,
            "selected_nodes": [
                {
                    "uuid": node.uuid,
                    "name": node.name,
                    "labels": node.labels,
                    "entity_id": node.entity_id,
                }
                for node in resolved
            ],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_selected_nodes(
        self, project_id: str, node_uuids: list[str]
    ) -> list[_ResolvedNode]:
        wanted = {u for u in node_uuids if u}
        if not wanted:
            return []
        all_nodes = self._graph_repo.load_all_nodes(project_id)
        picked = [n for n in all_nodes if n["uuid"] in wanted]

        resolved: list[_ResolvedNode] = []
        for node in picked:
            entity_id = self._entity_repo.resolve_entity_id(
                project_id, node["name"]
            )
            resolved.append(
                _ResolvedNode(
                    uuid=node["uuid"],
                    name=node["name"],
                    labels=node.get("labels") or [],
                    summary=node.get("summary") or "",
                    attributes=node.get("attributes") or {},
                    entity_id=entity_id,
                )
            )
        return resolved

    def _invoke_llm(
        self,
        nodes: list[_ResolvedNode],
        generate_bonds: bool,
        generate_threads: bool,
    ) -> dict[str, Any]:
        client = self._llm_router.build_client(MODULE_KEY)
        messages = _build_prompt(nodes, generate_bonds, generate_threads)
        payload = client.chat_json_value(messages, temperature=0.7, max_tokens=3000)
        return normalize_json_object(payload, "图谱羁绊/支线生成")

    def _persist_bonds(
        self,
        project_id: str,
        resolved: list[_ResolvedNode],
        bonds: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        by_name = {node.name: node for node in resolved}
        now = datetime.now(timezone.utc).isoformat()
        out: list[dict[str, Any]] = []

        for item in bonds:
            if not isinstance(item, dict):
                continue
            source_name = str(item.get("source_name") or "").strip()
            target_name = str(item.get("target_name") or "").strip()
            record = {
                "source_name": source_name,
                "target_name": target_name,
                "relation_type": str(item.get("relation_type") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "trust_level": _safe_float(item.get("trust_level")),
                "power_dynamic": str(item.get("power_dynamic") or "").strip(),
                "history": str(item.get("history") or "").strip(),
                "conflict_trigger": str(item.get("conflict_trigger") or "").strip(),
                "persisted": False,
                "relation_id": None,
                "skip_reason": "",
            }

            source_node = by_name.get(source_name)
            target_node = by_name.get(target_name)
            if not source_node or not target_node:
                record["skip_reason"] = "source/target 未落在所选节点集合内"
                out.append(record)
                continue
            if source_node.entity_id is None or target_node.entity_id is None:
                record["skip_reason"] = "节点未能映射到实体库"
                out.append(record)
                continue

            relation_id = f"rel_llmbond_{uuid.uuid4().hex[:10]}"
            try:
                self._relationship_repo.upsert_relationship(
                    project_id,
                    {
                        "relation_id": relation_id,
                        "source_id": source_node.entity_id,
                        "target_id": target_node.entity_id,
                        "relation_type": record["relation_type"] or "bond",
                        "description": record["description"],
                        "trust_level": record["trust_level"] or 0.0,
                        "power_dynamic": record["power_dynamic"],
                        "history": record["history"],
                        "conflict_trigger": record["conflict_trigger"],
                        "updated_at": now,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("upsert_relationship 失败")
                record["skip_reason"] = f"落库异常: {exc}"
            else:
                record["persisted"] = True
                record["relation_id"] = relation_id
            out.append(record)

        return out

    def _persist_threads(
        self,
        project_id: str,
        resolved: list[_ResolvedNode],
        threads: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        now = datetime.now(timezone.utc).isoformat()
        by_name = {node.name: node for node in resolved}
        out: list[dict[str, Any]] = []

        for item in threads:
            if not isinstance(item, dict):
                continue
            key_base = str(item.get("thread_key") or "").strip() or "llm_bond_thread"
            thread_key = f"llm::{key_base}::{uuid.uuid4().hex[:6]}"
            involved_names_raw = item.get("involved_names") or []
            if not isinstance(involved_names_raw, list):
                involved_names_raw = []
            involved_names = [
                str(n).strip() for n in involved_names_raw if str(n).strip()
            ]

            record = {
                "thread_key": thread_key,
                "detail": str(item.get("detail") or "").strip(),
                "status": str(item.get("status") or "open").strip() or "open",
                "involved_names": involved_names,
                "persisted": False,
                "thread_id": None,
                "linked_entity_ids": [],
                "skip_reason": "",
            }
            if record["status"] not in {"open", "progressed", "resolved"}:
                record["status"] = "open"

            try:
                created = self._thread_repo.create_thread(
                    project_id=project_id,
                    thread_key=record["thread_key"],
                    detail=record["detail"],
                    status=record["status"],
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("create_thread 失败")
                record["skip_reason"] = f"落库异常: {exc}"
                out.append(record)
                continue

            thread_id = created["thread_id"]
            linked: list[str] = []
            for name in involved_names:
                node = by_name.get(name)
                entity_id = node.entity_id if node else None
                if not entity_id:
                    entity_id = self._entity_repo.resolve_entity_id(project_id, name)
                if not entity_id:
                    continue
                try:
                    self._thread_repo.link_thread_entity(
                        project_id,
                        {
                            "thread_id": thread_id,
                            "entity_id": entity_id,
                            "role": "involved",
                            "created_at": now,
                        },
                    )
                    linked.append(entity_id)
                except Exception:  # noqa: BLE001
                    logger.exception("link_thread_entity 失败")

            record["persisted"] = True
            record["thread_id"] = thread_id
            record["linked_entity_ids"] = linked
            out.append(record)

        return out


# ------------------------------------------------------------------
# Prompt building
# ------------------------------------------------------------------

def _build_prompt(
    nodes: list[_ResolvedNode],
    generate_bonds: bool,
    generate_threads: bool,
) -> list[dict[str, str]]:
    node_lines: list[str] = []
    for idx, n in enumerate(nodes, start=1):
        attrs_brief = _brief_attributes(n.attributes)
        node_lines.append(
            f"{idx}. 名称: {n.name}\n"
            f"   类型标签: {', '.join(n.labels) if n.labels else '(无)'}\n"
            f"   摘要: {n.summary or '(无)'}\n"
            f"   其他属性: {attrs_brief}"
        )

    want_parts: list[str] = []
    if generate_bonds:
        want_parts.append("1-3 条羁绊 (bonds)")
    if generate_threads:
        want_parts.append("1-2 条支线剧情 (plot_threads)")
    want_text = " 与 ".join(want_parts)

    schema_parts: list[str] = []
    if generate_bonds:
        schema_parts.append(
            '"bonds": [{"source_name": string, "target_name": string, '
            '"relation_type": string, "description": string, '
            '"trust_level": number(-1~1), "power_dynamic": string, '
            '"history": string, "conflict_trigger": string}]'
        )
    if generate_threads:
        schema_parts.append(
            '"plot_threads": [{"thread_key": string, "detail": string, '
            '"status": "open"|"progressed"|"resolved", '
            '"involved_names": [string, ...]}]'
        )
    schema_text = "{ " + ", ".join(schema_parts) + " }"

    system = (
        "你是一个小说世界观编剧助手。你的唯一输出是 JSON，不要任何其他文字、解释或 Markdown 代码围栏。"
        "所有字段必须使用中文描述。"
    )

    user = (
        f"以下是故事图谱中的 {len(nodes)} 个节点：\n\n"
        + "\n\n".join(node_lines)
        + "\n\n"
        f"请基于这些节点，创作 {want_text}。约束：\n"
        "- bonds 中的 source_name / target_name 必须严格来自上述节点名称列表。\n"
        "- plot_threads.involved_names 列表中的名字也应尽量来自节点列表。\n"
        "- 羁绊要刻画具体的情感/立场/历史/冲突触发点，不空洞。\n"
        "- 支线剧情要有明确的冲突焦点和发展走向，detail 不少于 80 字。\n"
        "- thread_key 用简短英文/拼音短语（如 'hidden_pact' / 'xue_yuan'），detail 用中文。\n\n"
        f"严格按此 JSON 结构输出：{schema_text}"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _brief_attributes(attrs: dict[str, Any]) -> str:
    if not attrs:
        return "(无)"
    interesting = {
        k: attrs[k]
        for k in (
            "importance_tier",
            "entity_type",
            "faction",
            "aliases",
            "role",
            "archive_id",
        )
        if k in attrs and attrs[k]
    }
    if not interesting:
        return json.dumps(attrs, ensure_ascii=False)[:160]
    return json.dumps(interesting, ensure_ascii=False)


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
