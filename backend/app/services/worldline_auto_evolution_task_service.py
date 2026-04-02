"""世界线自动演化后台任务服务。"""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from ..models.task import TaskManager, TaskStatus
from .worldline_auto_action_service import WorldlineAutoActionService
from .worldline_auto_evolution_support import (
    MODE_FIRST_ROUND,
    PROCESSING_PROGRESS_BASE,
    TASK_TYPE,
    completion_message,
    latest_event,
    progress_detail,
    progress_percent,
    require_branch,
    resolve_branch_ids,
    resolve_container_dir,
    resolve_mode,
    resolve_steps,
    result_payload,
    stop_reason,
    task_metadata,
)


class WorldlineAutoEvolutionTaskService:
    def __init__(
        self,
        engine,
        runtime_service,
        memory_service,
        prepare_service=None,
        auto_action_service: Optional[WorldlineAutoActionService] = None,
    ):
        self.engine = engine
        self.runtime_service = runtime_service
        self.memory_service = memory_service
        self.prepare_service = prepare_service
        self.auto_action_service = auto_action_service or WorldlineAutoActionService()
        self._lock_guard = threading.Lock()
        self._session_locks: Dict[str, threading.Lock] = {}

    def start_tasks(
        self,
        session_id: str,
        project_id: Optional[str],
        graph_id: Optional[str],
        branch_ids: Optional[List[str]],
        mode: str,
        goal_text: str,
        max_steps: Optional[int],
    ) -> List[Dict[str, Any]]:
        session = self._require_session(session_id, project_id, graph_id)
        resolved_mode = resolve_mode(mode)
        resolved_branch_ids = resolve_branch_ids(session, branch_ids)
        resolved_steps = resolve_steps(resolved_mode, max_steps)
        tasks = []
        for branch_id in resolved_branch_ids:
            branch = require_branch(session, branch_id)
            task_id = TaskManager().create_task(
                TASK_TYPE,
                metadata=task_metadata(session, branch, resolved_mode, goal_text, resolved_steps),
            )
            self._start_worker(
                task_id,
                session.session_id,
                session.project_id,
                session.graph_id,
                branch.branch_id,
                branch.title,
                resolved_mode,
                goal_text.strip(),
                resolved_steps,
            )
            tasks.append({"branch_id": branch.branch_id, "branch_title": branch.title, "task_id": task_id})
        return tasks

    def _start_worker(
        self,
        task_id: str,
        session_id: str,
        project_id: Optional[str],
        graph_id: str,
        branch_id: str,
        branch_title: str,
        mode: str,
        goal_text: str,
        max_steps: int,
    ) -> None:
        thread = threading.Thread(
            target=self._run_worker,
            args=(task_id, session_id, project_id, graph_id, branch_id, branch_title, mode, goal_text, max_steps),
            daemon=True,
        )
        thread.start()

    def _run_worker(
        self,
        task_id: str,
        session_id: str,
        project_id: Optional[str],
        graph_id: str,
        branch_id: str,
        branch_title: str,
        mode: str,
        goal_text: str,
        max_steps: int,
    ) -> None:
        manager = TaskManager()
        manager.update_task(
                task_id,
                status=TaskStatus.PROCESSING,
                progress=PROCESSING_PROGRESS_BASE,
                message="世界线自动演化已启动",
                progress_detail=progress_detail(branch_id, branch_title, 0, max_steps, None, "running", None),
            )
        try:
            result = self._evolve_branch(
                task_id,
                session_id,
                project_id,
                graph_id,
                branch_id,
                branch_title,
                goal_text,
                max_steps,
            )
            manager.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                progress=100,
                message=completion_message(result["stop_reason"]),
                result=result,
                progress_detail=progress_detail(
                    branch_id,
                    branch_title,
                    result["completed_steps"],
                    max_steps,
                    result["latest_event"],
                    result["stop_reason"],
                    result["goal_verdict"],
                ),
            )
        except Exception as exc:
            manager.update_task(
                task_id,
                status=TaskStatus.FAILED,
                progress=100,
                message="世界线自动演化失败",
                error=str(exc),
                progress_detail=progress_detail(branch_id, branch_title, 0, max_steps, None, "failed", None),
            )

    def _evolve_branch(
        self,
        task_id: str,
        session_id: str,
        project_id: Optional[str],
        graph_id: str,
        branch_id: str,
        branch_title: str,
        goal_text: str,
        max_steps: int,
    ) -> Dict[str, Any]:
        completed_steps = 0
        goal_verdict = self.auto_action_service.empty_goal_verdict(goal_text)
        while completed_steps < max_steps:
            branch, agents, memory_hints, action_views = self._snapshot_branch(session_id, project_id, graph_id, branch_id, goal_text)
            action_plan = self.auto_action_service.generate_actions(branch, agents, goal_text, memory_hints, action_views)
            branch = self._apply_round(
                session_id,
                project_id,
                graph_id,
                branch_id,
                action_plan["actions"],
            )
            completed_steps += 1
            goal_verdict = self.auto_action_service.evaluate_goal(branch, goal_text)
            reason = stop_reason(completed_steps, max_steps, branch, action_plan["actions"], goal_verdict)
            self._update_processing_task(
                task_id,
                branch_id,
                branch_title,
                completed_steps,
                max_steps,
                branch,
                reason,
                goal_verdict,
            )
            if reason:
                return result_payload(branch, branch_id, completed_steps, reason, goal_verdict)
        raise RuntimeError(f"自动演化未按预期停止: {branch_id}")

    def _snapshot_branch(
        self,
        session_id: str,
        project_id: Optional[str],
        graph_id: str,
        branch_id: str,
        goal_text: str,
    ):
        with self._session_lock(session_id):
            session = self._require_session(session_id, project_id, graph_id)
            branch = require_branch(session, branch_id)
            container_dir = resolve_container_dir(self.engine, session, project_id)
            agents = self.runtime_service.list_agents(container_dir, session, branch.branch_id)
            memory_hints = self.memory_service.build_candidate_hints(
                container_dir,
                session.session_id,
                branch.branch_id,
                agents,
                goal_text,
            )
            action_views = {}
            if self.prepare_service is not None:
                action_views = self.prepare_service.build_action_views(container_dir, session, agents)
        return branch, agents, memory_hints, action_views

    def _apply_round(
        self,
        session_id: str,
        project_id: Optional[str],
        graph_id: str,
        branch_id: str,
        actions: List[Dict[str, str]],
    ):
        with self._session_lock(session_id):
            for action in actions:
                self.engine.queue_action(
                    session_id=session_id,
                    actor=action["agent_ref"],
                    action=action["action"],
                    intent=action["intent"],
                    target=action["target"],
                    project_id=project_id,
                    graph_id=graph_id,
                    branch_id=branch_id,
                )
            session = self.engine.step(
                session_id=session_id,
                project_id=project_id,
                graph_id=graph_id,
                branch_id=branch_id,
                steps=1,
                event_status="candidate",
            )
        return require_branch(session, branch_id)

    def _update_processing_task(
        self,
        task_id: str,
        branch_id: str,
        branch_title: str,
        completed_steps: int,
        max_steps: int,
        branch,
        stop_reason: Optional[str],
        goal_verdict: Dict[str, Any],
    ) -> None:
        TaskManager().update_task(
            task_id,
            status=TaskStatus.PROCESSING if not stop_reason else None,
            progress=progress_percent(completed_steps, max_steps),
            message="世界线自动演化中" if not stop_reason else completion_message(stop_reason),
            progress_detail=progress_detail(
                branch_id,
                branch_title,
                completed_steps,
                max_steps,
                latest_event(branch),
                stop_reason or "running",
                goal_verdict,
            ),
        )

    def _require_session(self, session_id: str, project_id: Optional[str], graph_id: Optional[str]):
        session = self.engine.get_session(session_id, project_id=project_id, graph_id=graph_id)
        if not session:
            raise ValueError(f"世界线会话不存在: {session_id}")
        return session

    def _session_lock(self, session_id: str) -> threading.Lock:
        with self._lock_guard:
            if session_id not in self._session_locks:
                self._session_locks[session_id] = threading.Lock()
            return self._session_locks[session_id]
