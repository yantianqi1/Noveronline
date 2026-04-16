"""世界线 agent 运行态服务。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, desc, insert, select, update

from ..database import get_engine
from ..repositories.worldline_runtime_repo import WorldlineRuntimeRepository
from ..tables.worldline import (
    agent_action_log,
    agent_dialogue_log,
    agent_registry,
    agent_state_snapshots,
    relation_state_log,
)
from .agents.memory import AgentMemoryService
from .agents.worldline import WorldlineAgentRegistry
from .worldline_single_world import current_world


def _now() -> str:
    return datetime.now().isoformat()


class WorldlineRuntimeService:
    """维护 agent 注册表、动作日志、对话日志和状态快照。"""

    def __init__(self, registry: Optional[WorldlineAgentRegistry] = None, memory_service: Optional[AgentMemoryService] = None):
        self.registry = registry or WorldlineAgentRegistry()
        self.memory_service = memory_service or AgentMemoryService()
        self._repo = WorldlineRuntimeRepository(get_engine())

    def ensure_session_runtime(self, container_dir: str, session) -> None:
        branch = current_world(session)
        tbl = agent_registry
        with self._repo.connect() as conn:
            row = conn.execute(
                select(tbl)
                .where(and_(tbl.c.session_id == session.session_id, tbl.c.branch_id == branch.branch_id))
                .limit(1)
            ).fetchone()
        if row:
            return
        self._bootstrap_session(session)

    def list_agents(self, container_dir: str, session, branch_id: str) -> List[Dict[str, Any]]:
        self.ensure_session_runtime(container_dir, session)
        tbl = agent_registry
        with self._repo.connect() as conn:
            rows = conn.execute(
                select(tbl)
                .where(and_(tbl.c.session_id == session.session_id, tbl.c.branch_id == branch_id))
                .order_by(tbl.c.display_name.asc())
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

    def record_action_queued(self, container_dir: str, session_id: str, branch_id: str, agent: Dict[str, Any], action_item, project_id: str = "") -> None:
        created_at = action_item.created_at
        tbl_action = agent_action_log
        tbl_reg = agent_registry
        with self._repo.connect() as conn:
            conn.execute(
                insert(tbl_action).prefix_with("OR REPLACE").values(
                    action_event_id=action_item.action_id,
                    project_id=project_id,
                    session_id=session_id,
                    branch_id=branch_id,
                    agent_id=agent["agent_id"],
                    display_name=agent["display_name"],
                    action=action_item.action,
                    intent=action_item.intent,
                    target=action_item.target,
                    source=action_item.source,
                    status="queued",
                    detail_json=json.dumps(action_item.to_dict(), ensure_ascii=False),
                    created_at=created_at,
                    applied_at=None,
                    discarded_at=None,
                )
            )
            conn.execute(
                update(tbl_reg)
                .where(and_(tbl_reg.c.session_id == session_id, tbl_reg.c.branch_id == branch_id, tbl_reg.c.agent_id == agent["agent_id"]))
                .values(last_action_at=created_at, updated_at=created_at)
            )
        self.memory_service.record_action_queued(container_dir, session_id, branch_id, agent, action_item, project_id=project_id)

    def record_step(self, container_dir: str, session, branch, step_result: Dict[str, Any]) -> None:
        self.ensure_session_runtime(container_dir, session)
        created_at = _now()
        agents = {item["agent_id"]: item for item in self.registry.list_agents(branch)}
        tbl_reg = agent_registry
        tbl_snap = agent_state_snapshots
        tbl_action = agent_action_log
        tbl_rel = relation_state_log
        project_id = getattr(session, "project_id", "") or ""
        with self._repo.connect() as conn:
            for item in agents.values():
                version = self._next_version(conn, session.session_id, branch.branch_id, item["agent_id"])
                conn.execute(
                    insert(tbl_snap).values(
                        snapshot_id=f"snap_{uuid.uuid4().hex[:16]}",
                        project_id=project_id,
                        session_id=session.session_id,
                        branch_id=branch.branch_id,
                        agent_id=item["agent_id"],
                        state_version=version,
                        status=item["status"],
                        reason="step",
                        state_json=json.dumps(item["state"], ensure_ascii=False),
                        created_at=created_at,
                    )
                )
                # Preserve existing last_dialogue_at and created_at from previous row
                existing = conn.execute(
                    select(tbl_reg.c.last_dialogue_at, tbl_reg.c.created_at)
                    .where(and_(tbl_reg.c.session_id == session.session_id, tbl_reg.c.branch_id == branch.branch_id, tbl_reg.c.agent_id == item["agent_id"]))
                    .limit(1)
                ).fetchone()
                prev_dialogue_at = existing.last_dialogue_at if existing else None
                prev_created_at = existing.created_at if existing else created_at

                reg_values = dict(
                    project_id=project_id,
                    session_id=session.session_id,
                    branch_id=branch.branch_id,
                    agent_id=item["agent_id"],
                    agent_kind=item["agent_kind"],
                    display_name=item["display_name"],
                    source_ref=item["source_ref"],
                    role=item["role"],
                    drive=item["drive"],
                    tension=item["tension"],
                    status=item["status"],
                    summary=item["summary"],
                    can_chat=int(bool(item["can_chat"])),
                    can_act=int(bool(item["can_act"])),
                    state_json=json.dumps(item["state"], ensure_ascii=False),
                    state_source=item.get("state_source", "session_bootstrap"),
                    state_version=version,
                    last_action_at=created_at if item["state"].get("last_action") else None,
                    last_dialogue_at=prev_dialogue_at,
                    source_archive_id=item.get("source_archive_id"),
                    source_entity_uuid=item.get("source_entity_uuid"),
                    importance_tier=item.get("importance_tier", "supporting"),
                    template_key=item.get("template_key", "generic.supporting.v1"),
                    template_version=item.get("template_version", "v1"),
                    template_sections_json=json.dumps(item.get("template_sections") or [], ensure_ascii=False),
                    created_at=prev_created_at,
                    updated_at=created_at,
                )
                if existing:
                    conn.execute(
                        update(tbl_reg)
                        .where(and_(tbl_reg.c.session_id == session.session_id, tbl_reg.c.branch_id == branch.branch_id, tbl_reg.c.agent_id == item["agent_id"]))
                        .values(**reg_values)
                    )
                else:
                    conn.execute(insert(tbl_reg).values(**reg_values))

            for action in step_result.get("consumed_actions", []):
                conn.execute(
                    update(tbl_action)
                    .where(tbl_action.c.action_event_id == action.action_id)
                    .values(status="applied", applied_at=created_at)
                )
            for relation in step_result.get("relation_changes", []):
                source_agent_id = self.registry.relation_endpoint_agent_id(branch, relation.get("source", ""))
                target_agent_id = self.registry.relation_endpoint_agent_id(branch, relation.get("target", ""))
                conn.execute(
                    insert(tbl_rel).values(
                        relation_event_id=f"rel_{uuid.uuid4().hex[:16]}",
                        project_id=project_id,
                        session_id=session.session_id,
                        branch_id=branch.branch_id,
                        agent_id=self.registry.relation_agent_id_from_names(branch, relation.get("source", ""), relation.get("target", "")),
                        source_agent_id=source_agent_id,
                        target_agent_id=target_agent_id,
                        source_name=relation.get("source", ""),
                        target_name=relation.get("target", ""),
                        change=relation.get("change", "stable"),
                        note=relation.get("note", ""),
                        status=relation.get("status", "active"),
                        last_action=relation.get("last_action", ""),
                        state_json=json.dumps(relation, ensure_ascii=False),
                        created_at=created_at,
                    )
                )
        self.memory_service.record_step(container_dir, session, branch, step_result, self.registry)

    def record_dialogue(self, container_dir: str, session, branch_id: str, agent: Dict[str, Any], message: str, result: Dict[str, Any], mode: str, model_name: str, context_summary: str) -> str:
        self.ensure_session_runtime(container_dir, session)
        dialogue_id = f"dlg_{uuid.uuid4().hex[:16]}"
        created_at = _now()
        tbl_dlg = agent_dialogue_log
        tbl_reg = agent_registry
        project_id = getattr(session, "project_id", "") or ""
        with self._repo.connect() as conn:
            conn.execute(
                insert(tbl_dlg).values(
                    dialogue_id=dialogue_id,
                    project_id=project_id,
                    session_id=session.session_id,
                    branch_id=branch_id,
                    agent_id=agent["agent_id"],
                    display_name=agent["display_name"],
                    message=message,
                    reply=result.get("reply", ""),
                    generator_mode=mode,
                    model_name=model_name,
                    context_summary=context_summary,
                    created_at=created_at,
                )
            )
            conn.execute(
                update(tbl_reg)
                .where(and_(tbl_reg.c.session_id == session.session_id, tbl_reg.c.branch_id == branch_id, tbl_reg.c.agent_id == agent["agent_id"]))
                .values(last_dialogue_at=created_at, updated_at=created_at)
            )
        self.memory_service.record_dialogue(container_dir, session, branch_id, agent, message, result, dialogue_id)
        return dialogue_id

    def list_actions(self, container_dir: str, session_id: str, branch_id: Optional[str], agent_id: Optional[str], status: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._query_items(agent_action_log, session_id, branch_id, agent_id, status, limit)

    def list_dialogues(self, container_dir: str, session_id: str, branch_id: Optional[str], agent_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._query_items(agent_dialogue_log, session_id, branch_id, agent_id, None, limit)

    def list_relation_history(self, container_dir: str, session_id: str, branch_id: Optional[str], agent_id: Optional[str], limit: int) -> List[Dict[str, Any]]:
        return self._query_items(relation_state_log, session_id, branch_id, agent_id, None, limit)

    def agent_history(self, container_dir: str, session_id: str, branch_id: str, agent_id: str, limit: int) -> Dict[str, Any]:
        tbl = agent_state_snapshots
        with self._repo.connect() as conn:
            snapshots = conn.execute(
                select(tbl)
                .where(and_(tbl.c.session_id == session_id, tbl.c.branch_id == branch_id, tbl.c.agent_id == agent_id))
                .order_by(desc(tbl.c.created_at))
                .limit(limit)
            ).fetchall()
        return {
            "snapshots": [dict(row._mapping) | {"state": json.loads(row.state_json)} for row in snapshots],
            "actions": self.list_actions(container_dir, session_id, branch_id, agent_id, None, limit),
            "dialogues": self.list_dialogues(container_dir, session_id, branch_id, agent_id, limit),
        }

    def _bootstrap_session(self, session) -> None:
        created_at = session.created_at or _now()
        tbl_reg = agent_registry
        tbl_snap = agent_state_snapshots
        tbl_rel = relation_state_log
        tbl_action = agent_action_log
        project_id = getattr(session, "project_id", "") or ""
        with self._repo.connect() as conn:
            for branch in session.branches:
                for agent in self.registry.list_agents(branch):
                    reg_values = dict(
                        project_id=project_id,
                        session_id=session.session_id,
                        branch_id=branch.branch_id,
                        agent_id=agent["agent_id"],
                        agent_kind=agent["agent_kind"],
                        display_name=agent["display_name"],
                        source_ref=agent["source_ref"],
                        role=agent["role"],
                        drive=agent["drive"],
                        tension=agent["tension"],
                        status=agent["status"],
                        summary=agent["summary"],
                        can_chat=int(bool(agent["can_chat"])),
                        can_act=int(bool(agent["can_act"])),
                        state_json=json.dumps(agent["state"], ensure_ascii=False),
                        state_source=agent.get("state_source", "session_bootstrap"),
                        state_version=1,
                        last_action_at=None,
                        last_dialogue_at=None,
                        source_archive_id=agent.get("source_archive_id"),
                        source_entity_uuid=agent.get("source_entity_uuid"),
                        importance_tier=agent.get("importance_tier", "supporting"),
                        template_key=agent.get("template_key", "generic.supporting.v1"),
                        template_version=agent.get("template_version", "v1"),
                        template_sections_json=json.dumps(agent.get("template_sections") or [], ensure_ascii=False),
                        created_at=created_at,
                        updated_at=created_at,
                    )
                    existing = conn.execute(
                        select(tbl_reg)
                        .where(and_(tbl_reg.c.session_id == session.session_id, tbl_reg.c.branch_id == branch.branch_id, tbl_reg.c.agent_id == agent["agent_id"]))
                        .limit(1)
                    ).fetchone()
                    if existing:
                        conn.execute(
                            update(tbl_reg)
                            .where(and_(tbl_reg.c.session_id == session.session_id, tbl_reg.c.branch_id == branch.branch_id, tbl_reg.c.agent_id == agent["agent_id"]))
                            .values(**reg_values)
                        )
                    else:
                        conn.execute(insert(tbl_reg).values(**reg_values))

                    conn.execute(
                        insert(tbl_snap).values(
                            snapshot_id=f"snap_{uuid.uuid4().hex[:16]}",
                            project_id=project_id,
                            session_id=session.session_id,
                            branch_id=branch.branch_id,
                            agent_id=agent["agent_id"],
                            state_version=1,
                            status=agent["status"],
                            reason="bootstrap",
                            state_json=json.dumps(agent["state"], ensure_ascii=False),
                            created_at=created_at,
                        )
                    )
                for relation in branch.relationship_states:
                    conn.execute(
                        insert(tbl_rel).values(
                            relation_event_id=f"rel_{uuid.uuid4().hex[:16]}",
                            project_id=project_id,
                            session_id=session.session_id,
                            branch_id=branch.branch_id,
                            agent_id=self.registry.relation_agent_id_from_names(
                                branch,
                                relation.get("source", ""),
                                relation.get("target", ""),
                            ),
                            source_agent_id=relation.get("source_agent_id") or self.registry.relation_endpoint_agent_id(branch, relation.get("source", "")),
                            target_agent_id=relation.get("target_agent_id") or self.registry.relation_endpoint_agent_id(branch, relation.get("target", "")),
                            source_name=relation.get("source", ""),
                            target_name=relation.get("target", ""),
                            change=relation.get("change", "stable"),
                            note=relation.get("note", ""),
                            status=relation.get("status", "active"),
                            last_action=relation.get("last_action", ""),
                            state_json=json.dumps(relation, ensure_ascii=False),
                            created_at=created_at,
                        )
                    )
                for action in branch.pending_actions:
                    agent = self.registry.resolve_agent(branch, action.agent_id or action.actor)
                    if not agent:
                        continue
                    conn.execute(
                        insert(tbl_action).prefix_with("OR REPLACE").values(
                            action_event_id=action.action_id,
                            project_id=project_id,
                            session_id=session.session_id,
                            branch_id=branch.branch_id,
                            agent_id=agent["agent_id"],
                            display_name=agent["display_name"],
                            action=action.action,
                            intent=action.intent,
                            target=action.target,
                            source=action.source,
                            status="queued",
                            detail_json=json.dumps(action.to_dict(), ensure_ascii=False),
                            created_at=action.created_at,
                            applied_at=None,
                            discarded_at=None,
                        )
                    )

    def _agent_payload(self, row) -> Dict[str, Any]:
        payload = dict(row._mapping)
        payload["can_chat"] = bool(payload["can_chat"])
        payload["can_act"] = bool(payload["can_act"])
        payload["state"] = json.loads(payload["state_json"])
        payload["template_sections"] = json.loads(payload.get("template_sections_json") or "[]")
        return payload

    def _next_version(self, conn, session_id: str, branch_id: str, agent_id: str) -> int:
        tbl = agent_registry
        row = conn.execute(
            select(tbl.c.state_version)
            .where(and_(tbl.c.session_id == session_id, tbl.c.branch_id == branch_id, tbl.c.agent_id == agent_id))
        ).fetchone()
        return int(row.state_version) + 1 if row else 1

    def _query_items(self, tbl, session_id: str, branch_id: Optional[str], agent_id: Optional[str], status: Optional[str], limit: int) -> List[Dict[str, Any]]:
        clauses = [tbl.c.session_id == session_id]
        if branch_id:
            clauses.append(tbl.c.branch_id == branch_id)
        if agent_id:
            clauses.append(tbl.c.agent_id == agent_id)
        if status and tbl is agent_action_log:
            clauses.append(tbl.c.status == status)
        stmt = (
            select(tbl)
            .where(and_(*clauses))
            .order_by(desc(tbl.c.created_at))
            .limit(max(1, min(limit, 100)))
        )
        with self._repo.connect() as conn:
            rows = conn.execute(stmt).fetchall()
        items = [dict(row._mapping) for row in rows]
        for item in items:
            if "detail_json" in item:
                item["detail"] = json.loads(item["detail_json"])
            if "state_json" in item:
                item["state"] = json.loads(item["state_json"])
        return items
