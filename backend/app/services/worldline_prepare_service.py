"""世界线 LLM prepare 生命周期服务。"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..database import get_engine
from ..models.task import TaskManager, TaskStatus
from ..models.worldline import WorldlineSession
from ..repositories.worldline_prepare_repo import WorldlinePrepareRepository
from .llm_router import LlmRouter


TASK_TYPE = "worldline_prepare"
STAGES = ("load_sources", "materialize_agents", "validate_dossiers", "compose_world_snapshot", "ready_to_start")
MODULE_KEY = "worldline_agent_prepare"


def _as_dict(value) -> dict:
    """Coerce LLM output to dict; tolerate list/str/None."""
    if isinstance(value, dict):
        return value
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict):
        return value[0]
    return {}


def _as_list(value) -> list:
    """Coerce LLM output to list; tolerate dict/str/None."""
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _as_dict_or_list(value):
    """Accept dict or list from LLM — pass through whichever it is."""
    if isinstance(value, (dict, list)):
        return value
    return {}


class WorldlinePrepareService:
    def __init__(self, engine, llm_router: Optional[LlmRouter] = None):
        self.engine = engine
        self.llm_router = llm_router or LlmRouter()
        self._repo = WorldlinePrepareRepository(get_engine())

    async def start_prepare(self, **payload) -> Dict[str, str]:
        resolved, container_dir, source, question, world_variables = self._resolve_prepare_context(payload)
        prepare_id = f"prep_{uuid.uuid4().hex[:12]}"
        task_id = await TaskManager().create_task(TASK_TYPE, metadata={"prepare_id": prepare_id, "project_id": resolved["project_id"]})
        now = self._now()
        self._repo.save_run(self._encode_run({
            "prepare_id": prepare_id,
            "task_id": task_id,
            "label": payload.get("label", ""),
            "project_id": resolved["project_id"],
            "graph_id": resolved["graph_id"],
            "session_scope": resolved["session_scope"],
            "status": "preparing",
            "stage": STAGES[0],
            "can_start": False,
            "focus_question": question,
            "branch_count": 1,
            "source_summary": source["source_summary"],
            "source": source,
            "world_variables": [item.to_dict() for item in world_variables],
            "input_payload": dict(payload),
            "source_archive_ids": list(resolved["source_archive_ids"]),
            "source_project_ids": list(resolved["source_project_ids"]),
            "source_archive_count": resolved["source_archive_count"],
            "started_session_id": "",
            "error": None,
            "created_at": now,
            "updated_at": now,
        }))
        self._append_event(prepare_id, STAGES[0], "info", "开始加载世界线源输入", {"graph_id": resolved["graph_id"]})
        self._start_worker(task_id, prepare_id, container_dir)
        return {"prepare_id": prepare_id, "task_id": task_id}

    def get_prepare(self, prepare_id: str, project_id: Optional[str] = None, graph_id: Optional[str] = None) -> Tuple[Dict[str, Any], str]:
        return self._load_run(prepare_id, project_id, graph_id)

    def list_prepare_agents(self, prepare_id: str, project_id: Optional[str] = None, graph_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        run, container_dir = self._load_run(prepare_id, project_id, graph_id)
        agents = [self._decode_dossier(d) for d in self._repo.list_dossiers(prepare_id)]
        return agents, run

    def get_dossier_for_session(self, container_dir: str, session, agent_id: str) -> Optional[Dict[str, Any]]:
        if not getattr(session, "prepare_id", ""):
            return None
        dossier = self._repo.get_dossier(session.prepare_id, agent_id)
        if not dossier:
            return None
        return self._decode_dossier(dossier) | {"prepare_id": session.prepare_id}

    def start_session(self, prepare_id: str, project_id: Optional[str] = None, graph_id: Optional[str] = None) -> Tuple[WorldlineSession, Dict[str, Any]]:
        run, container_dir = self._load_run(prepare_id, project_id, graph_id)
        if run["status"] != "ready" or not run["can_start"]:
            raise ValueError("prepare 尚未完成，当前不能开始推演")
        if run.get("started_session_id"):
            session = self.engine.get_session(run["started_session_id"], project_id=run.get("project_id"), graph_id=run["graph_id"])
            if session:
                return session, run
        dossiers = [self._decode_dossier(d) for d in self._repo.list_dossiers(prepare_id)]
        world_variables = self.engine.branch_service.normalize_variables(run.get("world_variables", []))
        branches = self.engine.branch_service.build_branches(run["branch_count"], run["source"], run["focus_question"], world_variables)
        self._apply_dossiers(branches[0], dossiers)
        session = WorldlineSession(
            session_id=f"ws_{datetime.now().strftime('%Y%m%d%H%M%S%f')[:20]}",
            project_id=run.get("project_id"),
            graph_id=run["graph_id"],
            simulation_goal=run["focus_question"],
            focus_question=run["focus_question"],
            branch_count=len(branches),
            label=run.get("label", ""),
            prepare_id=prepare_id,
            session_scope=run["session_scope"],
            branches=branches,
            world_variables=world_variables,
            timeline_focus=list(run["source"].get("timeline_focus", [])),
            agent_behavior_axes=list(run["source"].get("agent_behavior_axes", [])),
            source_summary=dict(run.get("source_summary", {})),
            source_archive_ids=list(run.get("source_archive_ids", [])),
            source_project_ids=list(run.get("source_project_ids", [])),
            source_archive_count=int(run.get("source_archive_count", 0)),
        )
        self.engine.store.save_session(container_dir, session)
        self.engine.runtime_service.ensure_session_runtime(container_dir, session)
        updated = run | {"started_session_id": session.session_id, "updated_at": self._now()}
        self._repo.save_run(self._encode_run(updated))
        self._append_event(prepare_id, STAGES[-1], "info", "prepare 结果已启动为 session", {"session_id": session.session_id})
        return session, updated

    def build_dialogue_bundle(self, container_dir: str, session, agent: Dict[str, Any]) -> Dict[str, Any]:
        dossier = self.get_dossier_for_session(container_dir, session, agent["agent_id"])
        if not dossier:
            return {}
        peers = []
        for item in [self._decode_dossier(d) for d in self._repo.list_dossiers(session.prepare_id)]:
            if item["agent_id"] == agent["agent_id"]:
                continue
            peers.append({"agent_id": item["agent_id"], "display_name": item["display_name"], "agent_kind": item["agent_kind"], "public_profile": item["public_profile"]})
        return {"self_dossier": dossier, "visible_peers": peers}

    def build_action_views(self, container_dir: str, session, agents: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        if not getattr(session, "prepare_id", ""):
            return {}
        dossiers = {item["agent_id"]: item for item in [self._decode_dossier(d) for d in self._repo.list_dossiers(session.prepare_id)]}
        return {
            agent["agent_id"]: {
                "display_name": agent["display_name"],
                "public_profile": dossiers.get(agent["agent_id"], {}).get("public_profile", {}),
                "relationship_view": dossiers.get(agent["agent_id"], {}).get("relationship_view", {}),
            }
            for agent in agents
        }

    def _start_worker(self, task_id: str, prepare_id: str, container_dir: str) -> None:
        asyncio.create_task(self._run_prepare(task_id, prepare_id, container_dir))

    async def _run_prepare(self, task_id: str, prepare_id: str, container_dir: str) -> None:
        manager = TaskManager()
        try:
            run = self._decode_run(self._repo.get_run(prepare_id))
            await self._update_task(manager, task_id, 10, "世界线 prepare：已加载源输入", STAGES[0], {})
            branch = self._prepare_branch(run)
            agents = self.engine.runtime_service.registry.list_agents(branch)
            client = self.llm_router.build_client(MODULE_KEY)
            self._append_event(prepare_id, STAGES[1], "info", "开始物化 agent dossier", {"agent_count": len(agents)})
            await self._materialize_dossiers(
                manager,
                task_id,
                prepare_id,
                run,
                branch,
                agents,
                client,
            )
            run = (self._decode_run(self._repo.get_run(prepare_id)) or {}) | {"status": "ready", "stage": STAGES[-1], "can_start": True, "updated_at": self._now()}
            self._repo.save_run(self._encode_run(run))
            self._append_event(prepare_id, STAGES[2], "info", "所有 dossier 校验通过", {"agent_count": len(agents)})
            self._append_event(prepare_id, STAGES[3], "info", "已完成世界启动快照组装", {})
            self._append_event(prepare_id, STAGES[4], "info", "prepare 已完成，可开始推演", {})
            await manager.update_task(task_id, status=TaskStatus.COMPLETED, progress=100, message="世界线 prepare 已完成", result={"prepare_id": prepare_id}, progress_detail={"stage": STAGES[-1], "prepare_id": prepare_id})
        except Exception as exc:
            run = self._decode_run(self._repo.get_run(prepare_id))
            if run:
                self._repo.save_run(self._encode_run(run | {"status": "failed", "stage": run.get("stage", STAGES[0]), "can_start": False, "error": str(exc), "updated_at": self._now()}))
                self._append_event(prepare_id, run.get("stage", STAGES[0]), "error", "prepare 失败", {"error": str(exc)})
            await manager.update_task(task_id, status=TaskStatus.FAILED, progress=100, message="世界线 prepare 失败", error=str(exc), progress_detail={"stage": STAGES[0], "prepare_id": prepare_id})

    def _prepare_branch(self, run: Dict[str, Any]):
        variables = self.engine.branch_service.normalize_variables(
            run.get("world_variables", [])
        )
        return self.engine.branch_service.build_branches(
            1,
            run["source"],
            run["focus_question"],
            variables,
        )[0]

    def _resolve_prepare_context(self, payload: Dict[str, Any]):
        resolved = self.engine._resolve_session_seed(payload.get("project_id"), payload.get("graph_id"), payload.get("archives"), payload.get("archive_ids"))
        resolved_project_id, container_dir = self.engine.store.resolve_container(resolved["project_id"], resolved["graph_id"], session_scope=resolved["session_scope"])
        source = self.engine.source_loader.load(resolved["project"], resolved["graph_id"], container_dir, resolved["archives"], payload.get("entity_types"), payload.get("config"))
        question = self.engine._focus_question(resolved["project"], payload.get("focus_question"))
        world_variables = self.engine.branch_service.normalize_variables(payload.get("variables", []) or [])
        return resolved | {"project_id": resolved_project_id}, container_dir, source, question, world_variables

    def _build_dossier(self, client, agent: Dict[str, Any], branch, run: Dict[str, Any]) -> Dict[str, Any]:
        prompt = (
            f"世界线目标：{run['focus_question']}\n"
            f"当前世界核心偏移：{branch.core_change}\n"
            f"agent 名称：{agent['display_name']}\n"
            f"agent 类型：{agent['agent_kind']}\n"
            f"基础状态：{agent['state']}\n"
            f"模板分级：{agent['template_key']} / {agent['template_sections']}\n"
            "请输出 JSON，包含：public_profile、private_profile、runtime_seed_state、relationship_view、memory_seed_summary、source_evidence_summary。"
        )
        payload = client.chat_json(
            messages=[
                {"role": "system", "content": "你是一位小说世界线整备导演。只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=1400,
        )
        raw_seed = payload.get("runtime_seed_state")
        runtime_seed_state = dict(agent["state"]) | (raw_seed if isinstance(raw_seed, dict) else {})
        runtime_seed_state.update(
            {
                "agent_kind": agent["agent_kind"],
                "importance_tier": agent.get("importance_tier", "supporting"),
                "template_key": agent.get("template_key", ""),
                "template_version": agent.get("template_version", "v1"),
                "template_sections": list(agent.get("template_sections") or []),
                "state_source": "prepared_dossier",
            }
        )
        validation_errors = self.engine.runtime_service.registry.schema_registry.validate_state(agent["agent_kind"], runtime_seed_state)
        now = self._now()
        return {
            "agent_id": agent["agent_id"],
            "agent_kind": agent["agent_kind"],
            "display_name": agent["display_name"],
            "source_archive_id": agent.get("source_archive_id") or "",
            "source_entity_uuid": agent.get("source_entity_uuid") or "",
            "importance_tier": agent.get("importance_tier", "supporting"),
            "template_key": agent.get("template_key", ""),
            "template_version": agent.get("template_version", "v1"),
            "template_sections": list(agent.get("template_sections") or []),
            "model_name": getattr(client, "model", ""),
            "validation_errors": validation_errors,
            "public_profile": _as_dict(payload.get("public_profile")),
            "private_profile": _as_dict(payload.get("private_profile")),
            "runtime_seed_state": runtime_seed_state,
            "relationship_view": _as_dict_or_list(payload.get("relationship_view")),
            "memory_seed_summary": _as_list(payload.get("memory_seed_summary")),
            "source_evidence_summary": _as_list(payload.get("source_evidence_summary")),
            "created_at": now,
            "updated_at": now,
        }

    async def _materialize_dossiers(
        self,
        manager: TaskManager,
        task_id: str,
        prepare_id: str,
        run: Dict[str, Any],
        branch,
        agents: List[Dict[str, Any]],
        client,
    ) -> None:
        completed = 0
        max_workers = self._prepare_max_workers(client, len(agents))
        sem = asyncio.Semaphore(max_workers)

        async def _bounded(agent: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
            async with sem:
                dossier = await asyncio.to_thread(
                    self._build_dossier_for_agent, agent, branch, run
                )
                return agent, dossier

        tasks = [_bounded(agent) for agent in agents]
        for coro in asyncio.as_completed(tasks):
            agent, dossier = await coro
            completed += 1
            self._repo.save_dossier(prepare_id, self._encode_dossier(dossier))
            self._append_event(
                prepare_id,
                STAGES[1],
                "info",
                f"完成 agent 整备：{agent['display_name']}",
                {"agent_id": agent["agent_id"]},
            )
            await self._update_task(
                manager,
                task_id,
                10 + int((completed / max(len(agents), 1)) * 55),
                "世界线 prepare：正在整备 agent",
                STAGES[1],
                {
                    "current": completed,
                    "total": len(agents),
                    "agent_id": agent["agent_id"],
                },
            )

    def _build_dossier_for_agent(
        self,
        agent: Dict[str, Any],
        branch,
        run: Dict[str, Any],
    ) -> Dict[str, Any]:
        client = self.llm_router.build_client(MODULE_KEY)
        return self._build_dossier(client, agent, branch, run)

    def _prepare_max_workers(self, client, agent_count: int) -> int:
        configured = int(getattr(client, "max_concurrency", 1) or 1)
        return min(max(configured, 1), max(agent_count, 1))

    def _apply_dossiers(self, branch, dossiers: List[Dict[str, Any]]) -> None:
        actors: Dict[str, Dict[str, Any]] = {}
        organizations: Dict[str, Dict[str, Any]] = {}
        relationships: List[Dict[str, Any]] = []
        for dossier in dossiers:
            payload = dict(dossier["runtime_seed_state"])
            if dossier["agent_kind"] == "character":
                actors[dossier["display_name"]] = payload
                continue
            if dossier["agent_kind"] == "organization":
                organizations[dossier["display_name"]] = payload
                continue
            relationships.append(payload)
        branch.actor_states = actors
        branch.organization_states = organizations
        branch.relationship_states = relationships

    def _load_run(self, prepare_id: str, project_id: Optional[str], graph_id: Optional[str]) -> Tuple[Dict[str, Any], str]:
        row = self._repo.get_run(prepare_id)
        if not row:
            raise ValueError(f"prepare 不存在: {prepare_id}")
        run = self._decode_run(row)
        # container_dir is still needed by callers for filesystem-based state
        for container_dir in self.engine.store._candidate_containers(project_id or run.get("project_id"), graph_id or run.get("graph_id")):
            return run, container_dir
        raise ValueError(f"prepare 不存在: {prepare_id}")

    async def _update_task(self, manager: TaskManager, task_id: str, progress: int, message: str, stage: str, detail: Dict[str, Any]) -> None:
        await manager.update_task(task_id, status=TaskStatus.PROCESSING, progress=progress, message=message, progress_detail={"stage": stage} | detail)

    def _append_event(self, prepare_id: str, stage: str, level: str, message: str, detail: Dict[str, Any]) -> None:
        self._repo.append_event({
            "event_id": f"prep_evt_{uuid.uuid4().hex[:12]}",
            "prepare_id": prepare_id,
            "stage": stage,
            "level": level,
            "message": message,
            "detail_json": json.dumps(detail, ensure_ascii=False),
            "created_at": self._now(),
        })

    def _now(self) -> str:
        return datetime.now().isoformat()

    # ------------------------------------------------------------------
    # JSON encode/decode helpers for repo ↔ service dict translation
    # ------------------------------------------------------------------

    _RUN_JSON_FIELDS = {
        "source_summary": "source_summary_json",
        "source": "source_json",
        "world_variables": "world_variables_json",
        "input_payload": "input_payload_json",
        "source_archive_ids": "source_archive_ids_json",
        "source_project_ids": "source_project_ids_json",
    }

    _DOSSIER_JSON_FIELDS = {
        "template_sections": "template_sections_json",
        "validation_errors": "validation_errors_json",
        "public_profile": "public_profile_json",
        "private_profile": "private_profile_json",
        "runtime_seed_state": "runtime_seed_state_json",
        "relationship_view": "relationship_view_json",
        "memory_seed_summary": "memory_seed_summary_json",
        "source_evidence_summary": "source_evidence_summary_json",
    }

    def _encode_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert service dict (plain keys) to repo dict (_json column names)."""
        out = dict(payload)
        for plain_key, json_key in self._RUN_JSON_FIELDS.items():
            if plain_key in out:
                out[json_key] = json.dumps(out.pop(plain_key), ensure_ascii=False)
        if "can_start" in out:
            out["can_start"] = int(bool(out["can_start"]))
        if "source_archive_count" in out:
            out["source_archive_count"] = int(out["source_archive_count"])
        # Remove keys not in the table
        out.pop("label", None)
        return out

    def _decode_run(self, row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Convert repo dict (_json column names) to service dict (plain keys)."""
        if not row:
            return None
        out = dict(row)
        for plain_key, json_key in self._RUN_JSON_FIELDS.items():
            if json_key in out:
                out[plain_key] = json.loads(out.pop(json_key) or "null")
        if "can_start" in out:
            out["can_start"] = bool(out["can_start"])
        return out

    def _encode_dossier(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Convert service dossier dict to repo dict with _json columns."""
        out = dict(payload)
        for plain_key, json_key in self._DOSSIER_JSON_FIELDS.items():
            if plain_key in out:
                out[json_key] = json.dumps(out.pop(plain_key), ensure_ascii=False)
        return out

    def _decode_dossier(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Convert repo dossier dict to service dict with plain keys."""
        out = dict(row)
        for plain_key, json_key in self._DOSSIER_JSON_FIELDS.items():
            if json_key in out:
                out[plain_key] = json.loads(out.pop(json_key) or "null")
        return out
