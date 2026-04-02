"""Worldline auto-evolve SSE streaming endpoint."""

from __future__ import annotations

import json
import traceback
from typing import Any, Dict, Generator

from flask import Response, request

from .worldline_support import (
    error,
    project_graph_from_request,
    worldline_bp,
    worldline_engine,
    worldline_memory_service,
    worldline_runtime_service,
)
from ..services.worldline_auto_action_service import WorldlineAutoActionService
from ..services.worldline_auto_evolution_support import (
    require_branch,
    resolve_branch_ids,
    resolve_container_dir,
    resolve_mode,
    resolve_steps,
    stop_reason,
)
from ..services.worldline_single_world import current_world


def _sse_event(event_type: str, data: Dict[str, Any]) -> str:
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _evolve_stream(
    session_id: str,
    project_id: str,
    graph_id: str,
    mode: str,
    goal_text: str,
    max_steps: int,
    constraints: list,
) -> Generator[str, None, None]:
    """Generator that yields SSE events during auto-evolution."""
    auto_action_service = WorldlineAutoActionService()

    session = worldline_engine.get_session(session_id, project_id=project_id, graph_id=graph_id)
    if not session:
        yield _sse_event("error", {"message": f"Session not found: {session_id}"})
        return

    resolved_mode = resolve_mode(mode)
    resolved_branch_ids = resolve_branch_ids(session, None)
    resolved_steps = resolve_steps(resolved_mode, max_steps)

    branch = current_world(session)
    branch_id = branch.branch_id

    # evolve_start
    yield _sse_event("evolve_start", {
        "step": branch.current_step + 1,
        "focus_agents": branch.key_agents[:5],
        "max_steps": resolved_steps,
        "constraints": constraints,
    })

    completed_steps = 0
    goal_verdict = auto_action_service.empty_goal_verdict(goal_text)
    candidate_events = []

    while completed_steps < resolved_steps:
        # Snapshot branch state
        session = worldline_engine.get_session(session_id, project_id=project_id, graph_id=graph_id)
        branch = require_branch(session, branch_id)
        container_dir = resolve_container_dir(worldline_engine, session, project_id)
        agents = worldline_runtime_service.list_agents(container_dir, session, branch.branch_id)

        memory_hints = worldline_memory_service.build_candidate_hints(
            container_dir, session.session_id, branch.branch_id, agents, goal_text,
        )

        # evolve_thinking: show which agents we're evaluating
        candidate_agent_names = [a["display_name"] for a in agents if a.get("can_act")][:4]
        thinking_factors = []
        if constraints:
            thinking_factors.append(f"用户约束: {'; '.join(constraints[:3])}")
        if branch.pending_variables:
            thinking_factors.append(f"待处理变量: {len(branch.pending_variables)} 条")
        if branch.pending_actions:
            thinking_factors.append(f"待执行动作: {len(branch.pending_actions)} 条")

        yield _sse_event("evolve_thinking", {
            "agent": candidate_agent_names[0] if candidate_agent_names else "system",
            "question": f"第 {branch.current_step + 1} 步：哪些角色应该在此刻做出决策？",
            "factors": thinking_factors or ["基于角色驱动力和当前世界状态评估"],
            "candidates": candidate_agent_names,
        })

        # Build constraint-enriched goal text
        enriched_goal = goal_text
        if constraints:
            constraint_block = "\n".join(f"- {c}" for c in constraints)
            enriched_goal = f"{goal_text}\n\n本轮约束条件：\n{constraint_block}"

        # Generate actions using LLM
        try:
            prepare_service = getattr(worldline_engine, 'prepare_service', None)
            action_views = {}
            if prepare_service is not None:
                action_views = prepare_service.build_action_views(container_dir, session, agents)

            action_plan = auto_action_service.generate_actions(
                branch, agents, enriched_goal, memory_hints, action_views,
            )
        except Exception:
            # If LLM call fails, use empty actions
            action_plan = {"actions": [], "model_name": ""}

        # Queue actions and step
        for action in action_plan["actions"]:
            worldline_engine.queue_action(
                session_id=session_id,
                actor=action["agent_ref"],
                action=action["action"],
                intent=action["intent"],
                target=action["target"],
                project_id=project_id,
                graph_id=graph_id,
                branch_id=branch_id,
            )

        session = worldline_engine.step(
            session_id=session_id,
            project_id=project_id,
            graph_id=graph_id,
            branch_id=branch_id,
            steps=1,
            event_status="candidate",
        )
        branch = require_branch(session, branch_id)
        completed_steps += 1

        # Get the newly created candidate event
        new_event = branch.timeline[-1] if branch.timeline else None
        if new_event and new_event.status == "candidate":
            event_data = new_event.to_dict()
            candidate_events.append(event_data)

            yield _sse_event("evolve_candidate", {
                "event_id": new_event.event_id,
                "actor": new_event.driving_entities[0] if new_event.driving_entities else "system",
                "action": new_event.title,
                "consequence": new_event.summary,
                "confidence": new_event.confidence,
                "confidence_reason": new_event.confidence_reason,
                "event_source": new_event.event_source,
                "step": new_event.step,
            })

        # Evaluate goal
        try:
            goal_verdict = auto_action_service.evaluate_goal(branch, goal_text)
        except Exception:
            goal_verdict = auto_action_service.empty_goal_verdict(goal_text)

        reason = stop_reason(completed_steps, resolved_steps, branch, action_plan["actions"], goal_verdict)
        if reason:
            break

    # evolve_done
    yield _sse_event("evolve_done", {
        "candidate_count": len(candidate_events),
        "completed_steps": completed_steps,
        "stop_reason": reason if 'reason' in dir() else "max_steps",
        "goal_verdict": goal_verdict,
    })

    # Final done event
    yield _sse_event("done", {
        "candidate_count": len(candidate_events),
        "session_id": session_id,
    })


@worldline_bp.route("/session/<session_id>/auto-evolve/stream", methods=["POST"])
def auto_evolve_stream(session_id: str):
    """SSE streaming endpoint for auto-evolution."""
    try:
        data = request.get_json() or {}
        project_id, graph_id = project_graph_from_request(data)
        mode = (data.get("mode") or "").strip() or "first_round"
        goal_text = str(data.get("goal_text") or "")
        max_steps = data.get("max_steps")
        constraints = data.get("constraints", [])

        if not isinstance(constraints, list):
            constraints = []

        return Response(
            _evolve_stream(
                session_id=session_id,
                project_id=project_id,
                graph_id=graph_id,
                mode=mode,
                goal_text=goal_text,
                max_steps=max_steps,
                constraints=constraints,
            ),
            content_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return error(str(exc), 500)
