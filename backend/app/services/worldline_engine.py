"""世界线演化引擎。"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import insert, select

from ..config import Config
from ..database import get_engine
from ..models.project import ProjectManager
from ..models.worldline import AgentAction, VariableInjection, WorldlineSession
from ..repositories.base import BaseRepository
from ..tables.novel import sessions, world_events, worldline_branches
from .agents.memory import AgentMemoryService
from .archive_library_service import ArchiveLibraryService
from .world_state_store import WorldStateStore
from .worldline_branch_comparison import WorldlineBranchComparisonService
from .worldline_branch_service import WorldlineBranchService
from .worldline_runtime_service import WorldlineRuntimeService
from .worldline_single_world import current_world, ensure_single_world_session, resolve_branch_id
from .worldline_source_loader import WorldlineSourceLoader

class WorldlineEngine:
    def __init__(
        self,
        store: WorldStateStore,
        source_loader: WorldlineSourceLoader,
        branch_service: WorldlineBranchService,
        comparison_service: WorldlineBranchComparisonService,
        archive_library: Optional[ArchiveLibraryService] = None,
        runtime_service: Optional[WorldlineRuntimeService] = None,
        memory_service: Optional[AgentMemoryService] = None,
    ):
        self.store = store
        self.source_loader = source_loader
        self.branch_service = branch_service
        self.comparison_service = comparison_service
        self.archive_library = archive_library or ArchiveLibraryService()
        self.memory_service = memory_service or AgentMemoryService()
        self.runtime_service = runtime_service or WorldlineRuntimeService(
            self.branch_service.agent_registry,
            memory_service=self.memory_service,
        )

    def create_session(
        self,
        project_id: Optional[str],
        graph_id: Optional[str],
        label: str = "",
        variables: Optional[List[Dict[str, Any]]] = None,
        focus_question: Optional[str] = None,
        branch_count: Optional[int] = None,
        archives: Optional[List[Dict[str, Any]]] = None,
        entity_types: Optional[List[str]] = None,
        config: Optional[Dict[str, Any]] = None,
        archive_ids: Optional[List[str]] = None,
    ) -> Tuple[WorldlineSession, str]:
        resolved = self._resolve_session_seed(project_id, graph_id, archives, archive_ids)
        resolved_project_id, container_dir = self.store.resolve_container(
            resolved["project_id"],
            resolved["graph_id"],
            session_scope=resolved["session_scope"],
        )
        source = self.source_loader.load(
            resolved["project"],
            resolved["graph_id"],
            container_dir,
            resolved["archives"],
            entity_types,
            config,
        )
        question = self._focus_question(resolved["project"], focus_question)
        branch_total = self._branch_count(branch_count, config)
        world_variables = self.branch_service.normalize_variables(variables or [])
        branches = self.branch_service.build_branches(branch_total, source, question, world_variables)
        session = WorldlineSession(
            session_id=f"ws_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:20]}",
            project_id=resolved_project_id,
            graph_id=resolved["graph_id"],
            simulation_goal=question,
            focus_question=question,
            branch_count=len(branches),
            label=label,
            session_scope=resolved["session_scope"],
            branches=branches,
            world_variables=world_variables,
            timeline_focus=source["timeline_focus"],
            agent_behavior_axes=source["agent_behavior_axes"],
            source_summary=source["source_summary"],
            source_archive_ids=list(resolved["source_archive_ids"]),
            source_project_ids=list(resolved["source_project_ids"]),
            source_archive_count=resolved["source_archive_count"],
        )
        self.store.save_session(container_dir, session)
        self.runtime_service.ensure_session_runtime(container_dir, session)
        return session, container_dir

    def step(
        self,
        session_id: str,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        steps: int = 1,
        evolution_intensity: str = "medium",
        custom_depth: Optional[int] = None,
        event_status: str = "canon",
        override_title: str = "",
        override_summary: str = "",
    ) -> WorldlineSession:
        session, container_dir = self._load_for_update(session_id, project_id, graph_id)
        for _ in range(max(1, min(steps, 10))):
            for branch in self._target_branches(session, branch_id):
                step_result = self.branch_service.advance_branch(
                    branch,
                    session,
                    evolution_intensity,
                    custom_depth,
                    event_status=event_status,
                    override_title=override_title,
                    override_summary=override_summary,
                )
                self.runtime_service.record_step(container_dir, session, branch, step_result)
        session.updated_at = datetime.now().isoformat()
        self.store.save_session(container_dir, session)
        self._sync_to_novel_db(session)
        return session

    def inject_variable(
        self,
        session_id: str,
        name: str,
        description: str,
        impact_axis: str = "",
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        branch_id: Optional[str] = None,
    ) -> WorldlineSession:
        if not name.strip():
            raise ValueError("变量名称不能为空")
        variable = VariableInjection(
            variable_id=f"var_{datetime.now().strftime('%H%M%S%f')[:10]}",
            name=name.strip(),
            description=description.strip() or name.strip(),
            impact_axis=impact_axis.strip(),
            source="manual_injection",
        )
        return self._apply_to_session(session_id, project_id, graph_id, branch_id, variable=variable)

    def inject_action(
        self,
        session_id: str,
        actor: str,
        action: str,
        intent: str = "",
        target: str = "",
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        agent_id: str = "",
    ) -> WorldlineSession:
        session, _ = self.queue_action(
            session_id=session_id,
            actor=actor,
            action=action,
            intent=intent,
            target=target,
            project_id=project_id,
            graph_id=graph_id,
            branch_id=branch_id,
            agent_id=agent_id,
        )
        return session

    def queue_action(
        self,
        session_id: str,
        actor: str,
        action: str,
        intent: str = "",
        target: str = "",
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        branch_id: Optional[str] = None,
        agent_id: str = "",
    ) -> tuple[WorldlineSession, List[str]]:
        if not action.strip():
            raise ValueError("action 不能为空")
        if not agent_id.strip() and not actor.strip():
            raise ValueError("agent_id 或 actor 不能为空")
        session, container_dir = self._load_for_update(session_id, project_id, graph_id)
        action_event_ids: List[str] = []
        for branch in self._target_branches(session, branch_id):
            agent = self._resolve_branch_agent(container_dir, session, branch, agent_id or actor)
            action_item = self._action_item(agent, action, intent, target)
            branch.pending_actions.append(action_item)
            branch.updated_at = action_item.created_at
            self.runtime_service.record_action_queued(
                container_dir,
                session.session_id,
                branch.branch_id,
                agent,
                action_item,
                project_id=getattr(session, "project_id", "") or "",
            )
            action_event_ids.append(action_item.action_id)
        session.updated_at = datetime.now().isoformat()
        self.store.save_session(container_dir, session)
        self._sync_to_novel_db(session)
        return session, action_event_ids

    def get_session(self, session_id: str, project_id: Optional[str] = None, graph_id: Optional[str] = None):
        try:
            session, _ = self._load_for_update(session_id, project_id, graph_id)
        except LookupError:
            return None
        return session

    def list_sessions(
        self,
        project_id: Optional[str] = None,
        graph_id: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        return self.store.list_sessions(project_id=project_id, graph_id=graph_id, limit=limit)

    def compare_branches(self, session_id: str, query: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        options = query or {}
        session = self.get_session(
            session_id,
            project_id=options.get("project_id"),
            graph_id=options.get("graph_id"),
        )
        if not session:
            raise LookupError(f"世界线会话不存在: {session_id}")
        return self.comparison_service.build(session, branch_ids=options.get("branch_ids"))

    def _resolve_session_seed(
        self,
        project_id: Optional[str],
        graph_id: Optional[str],
        archives: Optional[List[Dict[str, Any]]],
        archive_ids: Optional[List[str]],
    ) -> Dict[str, Any]:
        if archive_ids:
            return self._seed_from_archive_library(archive_ids)
        project, resolved_graph_id = self._resolve_project_and_graph(project_id, graph_id)
        session_scope = "project" if project else "global"
        return {
            "project": project,
            "project_id": project.project_id if project else None,
            "graph_id": resolved_graph_id,
            "archives": archives,
            "session_scope": session_scope,
            "source_archive_ids": [],
            "source_project_ids": [project.project_id] if project else [],
            "source_archive_count": len(archives or []),
        }

    def _seed_from_archive_library(self, archive_ids: List[str]) -> Dict[str, Any]:
        records = self.archive_library.resolve_archives(archive_ids)
        project_ids = sorted({item["project_id"] for item in records if item.get("project_id")})
        if len(project_ids) == 1:
            project = ProjectManager.get_project(project_ids[0])
            graph_id = (project.graph_id if project else "") or f"seed_project_{project_ids[0]}"
            session_scope = "project"
        else:
            project = None
            graph_id = self._global_graph_id(archive_ids)
            session_scope = "global"
        return {
            "project": project,
            "project_id": project.project_id if project else None,
            "graph_id": graph_id,
            "archives": [self._record_as_archive(record) for record in records],
            "session_scope": session_scope,
            "source_archive_ids": list(archive_ids),
            "source_project_ids": project_ids,
            "source_archive_count": len(records),
        }

    def _record_as_archive(self, record: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "archive_id": record.get("archive_id"),
            "entity_uuid": record["entity_uuid"],
            "entity_name": record["entity_name"],
            "entity_type": record["entity_type"],
            "agent_kind": record.get("agent_kind", "generic"),
            "importance_tier": record["importance_tier"],
            "recommended_importance_tier": record.get("recommended_importance_tier", record["importance_tier"]),
            "selected_importance_tier": record.get("selected_importance_tier", record["importance_tier"]),
            "template_key": record.get("template_key", "generic.supporting.v1"),
            "template_version": record.get("template_version", "v1"),
            "template_sections": list(record.get("template_sections", [])),
            "template_payload": dict(record.get("template_payload", {})),
            "template_metadata": dict(record.get("template_metadata", {})),
            "entity_role": record["entity_role"],
            "core_drive": record["core_drive"],
            "surface_mask": record["surface_mask"],
            "hidden_tension": record["hidden_tension"],
            "relationship_summary": record["relationship_summary"],
            "agent_behavior_hint": record["agent_behavior_hint"],
            "human_ai_relation_tag": record["human_ai_relation_tag"],
            "notable_risks": record["notable_risks"],
            "can_act_as_agent": record["can_act_as_agent"],
        }

    def _resolve_project_and_graph(self, project_id: Optional[str], graph_id: Optional[str]) -> tuple[Optional[Any], str]:
        if not project_id and not graph_id:
            raise ValueError("请提供 project_id 或 graph_id")
        project = ProjectManager.get_project(project_id) if project_id else None
        if project_id and not project:
            raise ValueError(f"项目不存在: {project_id}")
        resolved_graph_id = graph_id or (project.graph_id if project else None) or f"seed_project_{project_id}"
        if not resolved_graph_id:
            raise ValueError("未找到可用 graph_id")
        return project, resolved_graph_id

    def _focus_question(self, project: Optional[Any], focus_question: Optional[str]) -> str:
        if focus_question and focus_question.strip():
            return focus_question.strip()
        if project and project.analysis_goal:
            return project.analysis_goal
        return "观察变量扰动下的小说世界线演化"

    def _branch_count(self, branch_count: Optional[int], config: Optional[Dict[str, Any]]) -> int:
        del branch_count, config
        return 1

    def _apply_to_session(
        self,
        session_id: str,
        project_id: Optional[str],
        graph_id: Optional[str],
        branch_id: Optional[str],
        variable: Optional[VariableInjection] = None,
        action: Optional[AgentAction] = None,
    ) -> WorldlineSession:
        session, container_dir = self._load_for_update(session_id, project_id, graph_id)
        target_branches = self._target_branches(session, branch_id)
        if variable:
            session.world_variables.append(variable)
            for branch in target_branches:
                branch.pending_variables.append(variable)
                branch.updated_at = datetime.now().isoformat()
        if action:
            for branch in target_branches:
                branch.pending_actions.append(action)
                branch.updated_at = datetime.now().isoformat()
        session.updated_at = datetime.now().isoformat()
        self.store.save_session(container_dir, session)
        self._sync_to_novel_db(session)
        return session

    # ------------------------------------------------------------------
    # Sync worldline data to novel.sqlite3 for writer agent access
    # ------------------------------------------------------------------

    def _sync_to_novel_db(self, session: WorldlineSession) -> None:
        """Push branch metadata and timeline events to the centralised database.

        Uses INSERT OR REPLACE for sessions/branches (latest snapshot wins)
        and INSERT OR IGNORE for events (immutable).
        """
        project_id = session.project_id
        if not project_id:
            return
        try:
            now = datetime.now().isoformat()
            repo = BaseRepository(get_engine())
            with repo.connect() as conn:
                # Upsert session row
                existing = conn.execute(
                    select(sessions.c.session_id).where(
                        sessions.c.session_id == session.session_id
                    ).limit(1)
                ).fetchone()
                session_values = dict(
                    session_id=session.session_id,
                    project_id=project_id,
                    session_type="worldline",
                    title=getattr(session, "label", "") or getattr(session, "simulation_goal", ""),
                    focus_question=getattr(session, "focus_question", ""),
                    status=getattr(session, "status", "running"),
                    config_json="{}",
                    created_at=getattr(session, "created_at", now),
                    updated_at=getattr(session, "updated_at", now),
                )
                if existing:
                    from sqlalchemy import update
                    conn.execute(
                        update(sessions)
                        .where(sessions.c.session_id == session.session_id)
                        .values(**session_values)
                    )
                else:
                    conn.execute(insert(sessions).values(**session_values))

                for branch in session.branches:
                    # Upsert branch metadata
                    branch_existing = conn.execute(
                        select(worldline_branches.c.branch_id).where(
                            (worldline_branches.c.project_id == project_id)
                            & (worldline_branches.c.session_id == session.session_id)
                            & (worldline_branches.c.branch_id == branch.branch_id)
                        ).limit(1)
                    ).fetchone()
                    branch_values = dict(
                        project_id=project_id,
                        branch_id=branch.branch_id,
                        session_id=session.session_id,
                        title=branch.title,
                        core_change=branch.core_change,
                        narrative_value=getattr(branch, "narrative_value", ""),
                        current_step=branch.current_step,
                        status=branch.status,
                        evolution_intensity=getattr(branch, "evolution_intensity", "medium"),
                        evolution_depth=getattr(branch, "evolution_depth", 3),
                        key_agents_json=_json.dumps(branch.key_agents, ensure_ascii=False),
                        expected_conflicts_json=_json.dumps(branch.expected_conflicts, ensure_ascii=False),
                        actor_states_json=_json.dumps(branch.actor_states, ensure_ascii=False),
                        organization_states_json=_json.dumps(branch.organization_states, ensure_ascii=False),
                        relationship_states_json=_json.dumps(
                            [rs if isinstance(rs, dict) else {} for rs in branch.relationship_states],
                            ensure_ascii=False,
                        ),
                        created_at=getattr(branch, "created_at", now),
                        updated_at=getattr(branch, "updated_at", now),
                    )
                    if branch_existing:
                        from sqlalchemy import update
                        conn.execute(
                            update(worldline_branches)
                            .where(
                                (worldline_branches.c.project_id == project_id)
                                & (worldline_branches.c.session_id == session.session_id)
                                & (worldline_branches.c.branch_id == branch.branch_id)
                            )
                            .values(**branch_values)
                        )
                    else:
                        conn.execute(insert(worldline_branches).values(**branch_values))

                    # Append timeline events (immutable, INSERT OR IGNORE)
                    for event in branch.timeline:
                        conn.execute(
                            insert(world_events).prefix_with("OR IGNORE").values(
                                event_id=event.event_id,
                                project_id=project_id,
                                session_id=session.session_id,
                                branch_id=branch.branch_id,
                                step=event.step,
                                title=event.title,
                                summary=event.summary,
                                event_type=getattr(event, "event_type", "") or "",
                                driving_entities_json=_json.dumps(
                                    getattr(event, "driving_entities", []) or [],
                                    ensure_ascii=False,
                                ),
                                state_changes_json=_json.dumps(
                                    getattr(event, "state_changes", []) or [],
                                    ensure_ascii=False,
                                ),
                                status=getattr(event, "status", "canon") or "canon",
                                created_at=getattr(event, "created_at", now),
                            )
                        )
        except Exception:
            logging.getLogger(__name__).warning(
                "Failed to sync worldline session %s to database",
                session.session_id,
                exc_info=True,
            )

    def _load_for_update(
        self,
        session_id: str,
        project_id: Optional[str],
        graph_id: Optional[str],
    ) -> tuple[WorldlineSession, str]:
        session = self.store.load_session(session_id, project_id=project_id, graph_id=graph_id)
        if not session:
            raise LookupError(f"世界线会话不存在: {session_id}")
        _, container_dir = self.store.resolve_container(
            session.project_id or project_id,
            session.graph_id,
            session_scope=session.session_scope,
        )
        if self._repair_session_state(session):
            self.store.save_session(container_dir, session)
        self.runtime_service.ensure_session_runtime(container_dir, session)
        return session, container_dir

    def _repair_session_state(self, session: WorldlineSession) -> bool:
        changed = ensure_single_world_session(session)
        for branch in session.branches:
            changed |= self._repair_entity_states(branch.actor_states, branch.branch_id, session)
            changed |= self._repair_entity_states(branch.organization_states, branch.branch_id, session)
            changed |= self._repair_relationship_states(branch)
            changed |= self._repair_pending_actions(branch)
        return changed

    def _repair_entity_states(
        self,
        states: Dict[str, Dict[str, Any]],
        branch_id: str,
        session: WorldlineSession,
    ) -> bool:
        changed = False
        for state in states.values():
            changed |= self._setdefault(state, "branch_id", branch_id)
            changed |= self._setdefault(state, "session_scope", session.session_scope)
            changed |= self._setdefault(state, "graph_id", session.graph_id)
            changed |= self._setdefault(state, "state_source", "session_bootstrap")
        return changed

    def _repair_relationship_states(self, branch) -> bool:
        changed = False
        for relation in branch.relationship_states:
            changed |= self._setdefault(relation, "state_source", "session_bootstrap")
            if not relation.get("source_agent_id"):
                relation["source_agent_id"] = self.branch_service.agent_registry.relation_endpoint_agent_id(
                    branch,
                    relation.get("source", ""),
                )
                changed = True
            if not relation.get("target_agent_id"):
                relation["target_agent_id"] = self.branch_service.agent_registry.relation_endpoint_agent_id(
                    branch,
                    relation.get("target", ""),
                )
                changed = True
        return changed

    def _repair_pending_actions(self, branch) -> bool:
        changed = False
        for action in branch.pending_actions:
            if not action.agent_id:
                agent = self.branch_service.agent_registry.resolve_agent(branch, action.actor)
                if agent:
                    action.agent_id = agent["agent_id"]
                    changed = True
            if not action.actor and action.agent_id:
                agent = self.branch_service.agent_registry.resolve_agent(branch, action.agent_id)
                if agent:
                    action.actor = agent["display_name"]
                    changed = True
        return changed

    def _resolve_branch_agent(self, container_dir: str, session: WorldlineSession, branch, agent_ref: str) -> Dict[str, Any]:
        agent = self.runtime_service.resolve_agent(container_dir, session, branch.branch_id, agent_ref)
        if agent:
            return agent
        raise ValueError(f"世界线中不存在 agent: {agent_ref}")

    def _action_item(self, agent: Dict[str, Any], action: str, intent: str, target: str) -> AgentAction:
        return AgentAction(
            action_id=f"act_{uuid.uuid4().hex[:12]}",
            agent_id=agent["agent_id"],
            actor=agent["display_name"],
            action=action.strip(),
            intent=intent.strip(),
            target=target.strip(),
            source="manual_control",
        )

    def _setdefault(self, payload: Dict[str, Any], key: str, value: Any) -> bool:
        if payload.get(key) not in (None, ""):
            return False
        payload[key] = value
        return True

    def _target_branches(self, session: WorldlineSession, branch_id: Optional[str]):
        resolve_branch_id(branch_id)
        return [current_world(session)]

    def _global_graph_id(self, archive_ids: List[str]) -> str:
        joined = ",".join(sorted(archive_ids))
        digest = hashlib.sha1(joined.encode("utf-8")).hexdigest()[:12]
        return f"archive_mix_{digest}"
