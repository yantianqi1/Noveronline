"""世界线 agent 运行态服务。"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from .agent_memory_service import AgentMemoryService
from .worldline_agent_registry import WorldlineAgentRegistry
from .worldline_runtime_storage import WorldlineRuntimeStorage
from .worldline_single_world import current_world


def _now() -> str:
    return datetime.now().isoformat()


class WorldlineRuntimeService:
    """维护 agent 注册表、动作日志、对话日志和状态快照。"""

    def __init__(self, registry: Optional[WorldlineAgentRegistry] = None, memory_service: Optional[AgentMemoryService] = None):
        self.registry = registry or WorldlineAgentRegistry()
        self.memory_service = memory_service or AgentMemoryService()

    def runtime_db_path(self, container_dir: str) -> str:
        return WorldlineRuntimeStorage(container_dir).db_path

    def ensure_session_runtime(self, container_dir: str, session) -> None:
        branch = current_world(session)
        storage = WorldlineRuntimeStorage(container_dir)
        with storage.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM agent_registry WHERE session_id = ? AND branch_id = ? LIMIT 1",
                (session.session_id, branch.branch_id),
            ).fetchone()
        if row:
            return
        self._bootstrap_session(storage, session)

    def list_agents(self, container_dir: str, session, branch_id: str) -> List[Dict[str, Any]]:
        self.ensure_session_runtime(container_dir, session)
        storage = WorldlineRuntimeStorage(container_dir)
        with storage.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM agent_registry
                WHERE session_id = ? AND branch_id = ?
                ORDER BY display_name ASC
                """,
                (session.session_id, branch_id),
            ).fetchall()
        return [self._agent_payload(row) for row in rows]

    def resolve_agent(self, container_dir: str, session, branch_id: str, agent_ref: str) -> Optional[Dict[str, Any]]:
        text = (agent_ref or "").strip()
        if not text:
            return None
        for agent in self.list_agents(container_dir, session, branch_id):
            if text in {agent["agent_id"], agent["display_name"], agent["source_ref"]}:
                return agent
        return None

    def record_action_queued(self, container_dir: str, session_id: str, branch_id: str, agent: Dict[str, Any], action_item) -> None:
        storage = WorldlineRuntimeStorage(container_dir)
        created_at = action_item.created_at
        with storage.connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO agent_action_log (
                    action_event_id, session_id, branch_id, agent_id, display_name, action,
                    intent, target, source, status, detail_json, created_at, applied_at, discarded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                """,
                (
                    action_item.action_id,
                    session_id,
                    branch_id,
                    agent["agent_id"],
                    agent["display_name"],
                    action_item.action,
                    action_item.intent,
                    action_item.target,
                    action_item.source,
                    "queued",
                    json.dumps(action_item.to_dict(), ensure_ascii=False),
                    created_at,
                ),
            )
            connection.execute(
                """
                UPDATE agent_registry SET last_action_at = ?, updated_at = ?
                WHERE session_id = ? AND branch_id = ? AND agent_id = ?
                """,
                (created_at, created_at, session_id, branch_id, agent["agent_id"]),
            )
            connection.commit()
        self.memory_service.record_action_queued(container_dir, session_id, branch_id, agent, action_item)

    def record_step(self, container_dir: str, session, branch, step_result: Dict[str, Any]) -> None:
        self.ensure_session_runtime(container_dir, session)
        storage = WorldlineRuntimeStorage(container_dir)
        created_at = _now()
        agents = {item["agent_id"]: item for item in self.registry.list_agents(branch)}
        with storage.connect() as connection:
            for item in agents.values():
                version = self._next_version(connection, session.session_id, branch.branch_id, item["agent_id"])
                connection.execute(
                    """
                    INSERT INTO agent_state_snapshots (
                        snapshot_id, session_id, branch_id, agent_id, state_version, status, reason, state_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"snap_{uuid.uuid4().hex[:16]}",
                        session.session_id,
                        branch.branch_id,
                        item["agent_id"],
                        version,
                        item["status"],
                        "step",
                        json.dumps(item["state"], ensure_ascii=False),
                        created_at,
                    ),
                )
                connection.execute(
                    """
                    INSERT OR REPLACE INTO agent_registry (
                        session_id, branch_id, agent_id, agent_kind, display_name, source_ref, role, drive, tension,
                        status, summary, can_chat, can_act, state_json, state_source, state_version,
                        last_action_at, last_dialogue_at, source_archive_id, source_entity_uuid,
                        importance_tier, template_key, template_version, template_sections_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(
                        (SELECT last_dialogue_at FROM agent_registry WHERE session_id = ? AND branch_id = ? AND agent_id = ?),
                        NULL
                    ), ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM agent_registry WHERE session_id = ? AND branch_id = ? AND agent_id = ?), ?), ?)
                    """,
                    (
                        session.session_id,
                        branch.branch_id,
                        item["agent_id"],
                        item["agent_kind"],
                        item["display_name"],
                        item["source_ref"],
                        item["role"],
                        item["drive"],
                        item["tension"],
                        item["status"],
                        item["summary"],
                        int(bool(item["can_chat"])),
                        int(bool(item["can_act"])),
                        json.dumps(item["state"], ensure_ascii=False),
                        item.get("state_source", "session_bootstrap"),
                        version,
                        created_at if item["state"].get("last_action") else None,
                        session.session_id,
                        branch.branch_id,
                        item["agent_id"],
                        item.get("source_archive_id"),
                        item.get("source_entity_uuid"),
                        item.get("importance_tier", "supporting"),
                        item.get("template_key", "generic.supporting.v1"),
                        item.get("template_version", "v1"),
                        json.dumps(item.get("template_sections") or [], ensure_ascii=False),
                        session.session_id,
                        branch.branch_id,
                        item["agent_id"],
                        created_at,
                        created_at,
                    ),
                )
            for action in step_result.get("consumed_actions", []):
                connection.execute(
                    "UPDATE agent_action_log SET status = ?, applied_at = ? WHERE action_event_id = ?",
                    ("applied", created_at, action.action_id),
                )
            for relation in step_result.get("relation_changes", []):
                source_agent_id = self.registry.relation_endpoint_agent_id(branch, relation.get("source", ""))
                target_agent_id = self.registry.relation_endpoint_agent_id(branch, relation.get("target", ""))
                connection.execute(
                    """
                    INSERT INTO relation_state_log (
                        relation_event_id, session_id, branch_id, agent_id, source_agent_id, target_agent_id,
                        source_name, target_name, change, note, status, last_action, state_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"rel_{uuid.uuid4().hex[:16]}",
                        session.session_id,
                        branch.branch_id,
                        self.registry.relation_agent_id_from_names(branch, relation.get("source", ""), relation.get("target", "")),
                        source_agent_id,
                        target_agent_id,
                        relation.get("source", ""),
                        relation.get("target", ""),
                        relation.get("change", "stable"),
                        relation.get("note", ""),
                        relation.get("status", "active"),
                        relation.get("last_action", ""),
                        json.dumps(relation, ensure_ascii=False),
                        created_at,
                    ),
                )
            connection.commit()
        self.memory_service.record_step(container_dir, session, branch, step_result, self.registry)

    def record_dialogue(self, container_dir: str, session, branch_id: str, agent: Dict[str, Any], message: str, result: Dict[str, Any], mode: str, model_name: str, context_summary: str) -> str:
        self.ensure_session_runtime(container_dir, session)
        dialogue_id = f"dlg_{uuid.uuid4().hex[:16]}"
        created_at = _now()
        storage = WorldlineRuntimeStorage(container_dir)
        with storage.connect() as connection:
            connection.execute(
                """
                INSERT INTO agent_dialogue_log (
                    dialogue_id, session_id, branch_id, agent_id, display_name, message, reply,
                    generator_mode, model_name, context_summary, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dialogue_id,
                    session.session_id,
                    branch_id,
                    agent["agent_id"],
                    agent["display_name"],
                    message,
                    result.get("reply", ""),
                    mode,
                    model_name,
                    context_summary,
                    created_at,
                ),
            )
            connection.execute(
                """
                UPDATE agent_registry SET last_dialogue_at = ?, updated_at = ?
                WHERE session_id = ? AND branch_id = ? AND agent_id = ?
                """,
                (created_at, created_at, session.session_id, branch_id, agent["agent_id"]),
            )
            connection.commit()
        self.memory_service.record_dialogue(container_dir, session, branch_id, agent, message, result, dialogue_id)
        return dialogue_id

    def list_actions(self, container_dir: str, session_id: str, branch_id: Optional[str], agent_id: Optional[str], status: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._query_items(container_dir, "agent_action_log", session_id, branch_id, agent_id, status, limit, "created_at DESC")

    def list_dialogues(self, container_dir: str, session_id: str, branch_id: Optional[str], agent_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._query_items(container_dir, "agent_dialogue_log", session_id, branch_id, agent_id, None, limit, "created_at DESC")

    def list_relation_history(self, container_dir: str, session_id: str, branch_id: Optional[str], agent_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._query_items(container_dir, "relation_state_log", session_id, branch_id, agent_id, None, limit, "created_at DESC")

    def agent_history(self, container_dir: str, session_id: str, branch_id: str, agent_id: str, limit: int) -> Dict[str, Any]:
        storage = WorldlineRuntimeStorage(container_dir)
        with storage.connect() as connection:
            snapshots = connection.execute(
                """
                SELECT * FROM agent_state_snapshots
                WHERE session_id = ? AND branch_id = ? AND agent_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (session_id, branch_id, agent_id, limit),
            ).fetchall()
        return {
            "snapshots": [dict(row) | {"state": json.loads(row["state_json"])} for row in snapshots],
            "actions": self.list_actions(container_dir, session_id, branch_id, agent_id, None, limit),
            "dialogues": self.list_dialogues(container_dir, session_id, branch_id, agent_id, limit),
        }

    def _bootstrap_session(self, storage: WorldlineRuntimeStorage, session) -> None:
        created_at = session.created_at or _now()
        with storage.connect() as connection:
            for branch in session.branches:
                for agent in self.registry.list_agents(branch):
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO agent_registry (
                            session_id, branch_id, agent_id, agent_kind, display_name, source_ref, role, drive, tension,
                            status, summary, can_chat, can_act, state_json, state_source, state_version,
                            last_action_at, last_dialogue_at, source_archive_id, source_entity_uuid,
                            importance_tier, template_key, template_version, template_sections_json, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            session.session_id,
                            branch.branch_id,
                            agent["agent_id"],
                            agent["agent_kind"],
                            agent["display_name"],
                            agent["source_ref"],
                            agent["role"],
                            agent["drive"],
                            agent["tension"],
                            agent["status"],
                            agent["summary"],
                            int(bool(agent["can_chat"])),
                            int(bool(agent["can_act"])),
                            json.dumps(agent["state"], ensure_ascii=False),
                            agent.get("state_source", "session_bootstrap"),
                            agent.get("source_archive_id"),
                            agent.get("source_entity_uuid"),
                            agent.get("importance_tier", "supporting"),
                            agent.get("template_key", "generic.supporting.v1"),
                            agent.get("template_version", "v1"),
                            json.dumps(agent.get("template_sections") or [], ensure_ascii=False),
                            created_at,
                            created_at,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO agent_state_snapshots (
                            snapshot_id, session_id, branch_id, agent_id, state_version, status, reason, state_json, created_at
                        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
                        """,
                        (
                            f"snap_{uuid.uuid4().hex[:16]}",
                            session.session_id,
                            branch.branch_id,
                            agent["agent_id"],
                            agent["status"],
                            "bootstrap",
                            json.dumps(agent["state"], ensure_ascii=False),
                            created_at,
                        ),
                    )
                for relation in branch.relationship_states:
                    connection.execute(
                        """
                        INSERT INTO relation_state_log (
                            relation_event_id, session_id, branch_id, agent_id, source_agent_id, target_agent_id,
                            source_name, target_name, change, note, status, last_action, state_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            f"rel_{uuid.uuid4().hex[:16]}",
                            session.session_id,
                            branch.branch_id,
                            self.registry.relation_agent_id_from_names(
                                branch,
                                relation.get("source", ""),
                                relation.get("target", ""),
                            ),
                            relation.get("source_agent_id")
                            or self.registry.relation_endpoint_agent_id(branch, relation.get("source", "")),
                            relation.get("target_agent_id")
                            or self.registry.relation_endpoint_agent_id(branch, relation.get("target", "")),
                            relation.get("source", ""),
                            relation.get("target", ""),
                            relation.get("change", "stable"),
                            relation.get("note", ""),
                            relation.get("status", "active"),
                            relation.get("last_action", ""),
                            json.dumps(relation, ensure_ascii=False),
                            created_at,
                        ),
                    )
                for action in branch.pending_actions:
                    agent = self.registry.resolve_agent(branch, action.agent_id or action.actor)
                    if not agent:
                        continue
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO agent_action_log (
                            action_event_id, session_id, branch_id, agent_id, display_name, action,
                            intent, target, source, status, detail_json, created_at, applied_at, discarded_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL)
                        """,
                        (
                            action.action_id,
                            session.session_id,
                            branch.branch_id,
                            agent["agent_id"],
                            agent["display_name"],
                            action.action,
                            action.intent,
                            action.target,
                            action.source,
                            "queued",
                            json.dumps(action.to_dict(), ensure_ascii=False),
                            action.created_at,
                        ),
                    )
            connection.commit()

    def _agent_payload(self, row) -> Dict[str, Any]:
        payload = dict(row)
        payload["can_chat"] = bool(payload["can_chat"])
        payload["can_act"] = bool(payload["can_act"])
        payload["state"] = json.loads(payload["state_json"])
        payload["template_sections"] = json.loads(payload.get("template_sections_json") or "[]")
        return payload

    def _next_version(self, connection, session_id: str, branch_id: str, agent_id: str) -> int:
        row = connection.execute(
            """
            SELECT state_version FROM agent_registry
            WHERE session_id = ? AND branch_id = ? AND agent_id = ?
            """,
            (session_id, branch_id, agent_id),
        ).fetchone()
        return int(row["state_version"]) + 1 if row else 1

    def _query_items(self, container_dir: str, table: str, session_id: str, branch_id: Optional[str], agent_id: Optional[str], status: Optional[str], limit: int, order_by: str) -> List[Dict[str, Any]]:
        storage = WorldlineRuntimeStorage(container_dir)
        clauses = ["session_id = ?"]
        params: List[Any] = [session_id]
        if branch_id:
            clauses.append("branch_id = ?")
            params.append(branch_id)
        if agent_id:
            clauses.append("agent_id = ?")
            params.append(agent_id)
        if status and table == "agent_action_log":
            clauses.append("status = ?")
            params.append(status)
        sql = f"SELECT * FROM {table} WHERE {' AND '.join(clauses)} ORDER BY {order_by} LIMIT ?"
        params.append(max(1, min(limit, 100)))
        with storage.connect() as connection:
            rows = connection.execute(sql, params).fetchall()
        items = [dict(row) for row in rows]
        for item in items:
            if "detail_json" in item:
                item["detail"] = json.loads(item["detail_json"])
            if "state_json" in item:
                item["state"] = json.loads(item["state_json"])
        return items
