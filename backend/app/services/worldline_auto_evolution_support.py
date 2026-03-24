"""世界线自动演化任务辅助函数。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .worldline_single_world import MAIN_WORLD_BRANCH_ID, current_world, resolve_branch_id, resolve_branch_ids as resolve_single_world_branch_ids


TASK_TYPE = "worldline_auto_evolve_branch"
MODE_FIRST_ROUND = "first_round"
MODE_CONTINUOUS = "continuous"
VALID_MODES = {MODE_FIRST_ROUND, MODE_CONTINUOUS}
FIRST_ROUND_STEPS = 1
DEFAULT_CONTINUOUS_STEPS = 6
PROCESSING_PROGRESS_BASE = 8
PROCESSING_PROGRESS_CAP = 92


def stop_reason(
    completed_steps: int,
    max_steps: int,
    branch,
    generated_actions: List[Dict[str, str]],
    goal_verdict: Dict[str, Any],
) -> Optional[str]:
    if goal_verdict.get("goal_reached"):
        return "goal_reached"
    if completed_steps >= max_steps:
        return "max_steps"
    if not generated_actions and not branch.pending_variables and not branch.pending_actions:
        return "settled"
    return None


def progress_percent(completed_steps: int, max_steps: int) -> int:
    ratio = completed_steps / max(max_steps, 1)
    scaled = PROCESSING_PROGRESS_BASE + int(ratio * (PROCESSING_PROGRESS_CAP - PROCESSING_PROGRESS_BASE))
    return max(PROCESSING_PROGRESS_BASE, min(scaled, PROCESSING_PROGRESS_CAP))


def completion_message(reason: str) -> str:
    messages = {
        "goal_reached": "世界线自动演化已达成目标",
        "max_steps": "世界线自动演化达到步数上限",
        "settled": "世界线自动演化已自然收束",
    }
    return messages.get(reason, "世界线自动演化完成")


def progress_detail(
    branch_id: str,
    branch_title: str,
    completed_steps: int,
    max_steps: int,
    latest_event: Optional[Dict[str, Any]],
    reason: str,
    goal_verdict: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    return {
        "branch_id": branch_id,
        "branch_title": branch_title,
        "completed_steps": completed_steps,
        "max_steps": max_steps,
        "latest_event": latest_event,
        "stop_reason": reason,
        "goal_verdict": goal_verdict,
    }


def latest_event(branch) -> Optional[Dict[str, Any]]:
    latest = branch.timeline[-1] if branch.timeline else None
    return latest.to_dict() if latest else None


def result_payload(
    branch,
    branch_id: str,
    completed_steps: int,
    reason: str,
    goal_verdict: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "branch_id": branch_id,
        "status": "completed",
        "stop_reason": reason,
        "completed_steps": completed_steps,
        "latest_event": latest_event(branch),
        "goal_verdict": goal_verdict,
    }


def task_metadata(session, branch, mode: str, goal_text: str, max_steps: int) -> Dict[str, Any]:
    return {
        "session_id": session.session_id,
        "project_id": session.project_id,
        "graph_id": session.graph_id,
        "branch_id": branch.branch_id,
        "branch_title": branch.title,
        "mode": mode,
        "goal_text": goal_text,
        "max_steps": max_steps,
    }


def resolve_mode(mode: str) -> str:
    if mode not in VALID_MODES:
        raise ValueError("mode 必须是 first_round 或 continuous")
    return mode


def resolve_steps(mode: str, max_steps: Optional[int]) -> int:
    if mode == MODE_FIRST_ROUND:
        return FIRST_ROUND_STEPS
    candidate = max_steps if isinstance(max_steps, int) else DEFAULT_CONTINUOUS_STEPS
    if candidate < 1:
        raise ValueError("max_steps 必须是大于等于 1 的整数")
    return candidate


def resolve_branch_ids(session, branch_ids: Optional[List[str]]) -> List[str]:
    current_world(session)
    return resolve_single_world_branch_ids(branch_ids)


def require_branch(session, branch_id: str):
    current = current_world(session)
    resolve_branch_id(branch_id)
    return current


def resolve_container_dir(engine, session, project_id: Optional[str]) -> str:
    _, container_dir = engine.store.resolve_container(
        session.project_id or project_id,
        session.graph_id,
        session_scope=session.session_scope,
    )
    return container_dir
