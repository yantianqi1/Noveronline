"""Worldline auto-evolve SSE streaming endpoint."""

from __future__ import annotations

import json
import logging
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Generator, List

from flask import Response, request

from .worldline_support import (
    error,
    project_graph_from_request,
    worldline_bp,
    worldline_engine,
    worldline_memory_service,
    worldline_runtime_service,
)
from ..services.agents.worldline.character_agent_service import CharacterAgentService
from ..services.worldline_auto_action_service import WorldlineAutoActionService
from ..services.worldline_auto_evolution_support import (
    require_branch,
    resolve_branch_ids,
    resolve_container_dir,
    resolve_mode,
    resolve_steps,
    stop_reason,
)
from ..services.worldline_director_agent import WorldlineDirectorAgent, DirectorDecision, DIRECTOR_MODULE_KEY
from ..services.worldline_director_tools import DirectorToolExecutor
from ..services.worldline_single_world import current_world
from ..services.llm_router import LlmRouter

logger = logging.getLogger("mirofish.auto_evolution_sse")

CANDIDATE_LIMIT = 6


def _sse_event(event_type: str, data: Dict[str, Any]) -> str:
    payload = json.dumps({"type": event_type, **data}, ensure_ascii=False)
    return f"data: {payload}\n\n"


def _try_build_director(prepare_service) -> WorldlineDirectorAgent | None:
    """Try to build a director agent. Returns None if module not bound."""
    llm_router = LlmRouter()
    try:
        llm_router.build_client(DIRECTOR_MODULE_KEY)
    except ValueError:
        return None

    character_service = CharacterAgentService()
    tool_executor = DirectorToolExecutor(character_service, prepare_service)
    return WorldlineDirectorAgent(llm_router, tool_executor)


def _sorted_candidates(agents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actable = [a for a in agents if a.get("can_act")]
    actable.sort(key=lambda a: (1 if a.get("last_action_at") else 0, a.get("last_action_at") or ""))
    return actable[:CANDIDATE_LIMIT]


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
    character_service = CharacterAgentService()
    prepare_service = getattr(worldline_engine, "prepare_service", None)
    director_agent = _try_build_director(prepare_service)

    if director_agent:
        logger.info("使用天道模式：角色自主提案 → 导演裁决")
    else:
        logger.info("worldline_director 未绑定，使用传统动作生成模式")

    session = worldline_engine.get_session(session_id, project_id=project_id, graph_id=graph_id)
    if not session:
        yield _sse_event("error", {"message": f"Session not found: {session_id}"})
        return

    resolved_mode = resolve_mode(mode)
    resolve_branch_ids(session, None)
    resolved_steps = resolve_steps(resolved_mode, max_steps)

    logger.info("推演启动: mode=%s, resolved_steps=%d, goal=%s", resolved_mode, resolved_steps, goal_text[:60])

    branch = current_world(session)
    branch_id = branch.branch_id

    yield _sse_event("evolve_start", {
        "step": branch.current_step + 1,
        "focus_agents": branch.key_agents[:5],
        "max_steps": resolved_steps,
        "constraints": constraints,
    })

    completed_steps = 0
    consecutive_empty = 0
    goal_verdict = auto_action_service.empty_goal_verdict(goal_text)
    candidate_events: List[Dict[str, Any]] = []
    reason = ""

    while completed_steps < resolved_steps:
        session = worldline_engine.get_session(session_id, project_id=project_id, graph_id=graph_id)
        branch = require_branch(session, branch_id)
        container_dir = resolve_container_dir(worldline_engine, session, project_id)
        agents = worldline_runtime_service.list_agents(container_dir, session, branch.branch_id)

        memory_hints = worldline_memory_service.build_candidate_hints(
            container_dir, session.session_id, branch.branch_id, agents, goal_text,
        )

        enriched_goal = goal_text
        if constraints:
            constraint_block = "\n".join(f"- {c}" for c in constraints)
            enriched_goal = f"{goal_text}\n\n本轮约束条件：\n{constraint_block}"

        action_views: Dict[str, Dict[str, Any]] = {}
        if prepare_service is not None:
            action_views = prepare_service.build_action_views(container_dir, session, agents)

        decision: DirectorDecision | None = None
        action_plan: Dict[str, Any]

        if director_agent:
            # ═══ 天道模式：角色提案 → 导演裁决 ═══

            candidates = _sorted_candidates(agents)
            candidate_names = [a["display_name"] for a in candidates]

            # Step 1: 角色自主提案（并发）
            yield _sse_event("evolve_thinking", {
                "agent": "天道",
                "question": f"{len(candidates)} 个角色正在同时思考本步行动...",
                "factors": candidate_names[:6],
                "candidates": candidate_names,
            })

            # Prepare args for each candidate (must be done in main thread
            # because prepare_service may read SQLite)
            proposal_args: List[Dict[str, Any]] = []
            recent_events = []
            for evt in (branch.timeline or [])[-4:]:
                recent_events.append({
                    "title": getattr(evt, "title", "") or "",
                    "summary": getattr(evt, "summary", "") or "",
                })
            branch_summary = {"title": branch.title, "core_change": branch.core_change}

            for agent in candidates:
                actor_state = dict(agent.get("state") or {})
                actor_state.setdefault("drive", agent.get("drive", ""))
                actor_state.setdefault("tension", agent.get("tension", ""))
                actor_state.setdefault("status", agent.get("status", ""))
                actor_state.setdefault("role", agent.get("role", ""))

                dossier_context = {}
                if prepare_service:
                    try:
                        dossier_context = prepare_service.build_dialogue_bundle(container_dir, session, agent)
                    except Exception:
                        pass

                memory_bundle = {}
                hint = memory_hints.get(agent.get("agent_id", ""))
                if hint:
                    memory_bundle["rendered_context"] = hint

                proposal_args.append({
                    "actor_name": agent["display_name"],
                    "actor_state": actor_state,
                    "recent_events": recent_events,
                    "branch_summary": branch_summary,
                    "memory_bundle": memory_bundle,
                    "dossier_context": dossier_context,
                })

            # Fire all LLM calls concurrently
            def _make_proposal(args):
                try:
                    return character_service.propose_action(**args)
                except Exception:
                    logger.error("角色 %s 提案失败:\n%s", args["actor_name"], traceback.format_exc())
                    return {"agent": args["actor_name"], "act": False, "reason": "提案生成失败"}

            proposals: List[Dict[str, Any]] = []
            with ThreadPoolExecutor(max_workers=min(len(proposal_args), 6)) as pool:
                futures = {pool.submit(_make_proposal, args): args["actor_name"] for args in proposal_args}
                for future in as_completed(futures):
                    proposals.append(future.result())

            # Report results (after all complete)
            for proposal in proposals:
                agent_name = proposal.get("agent", "?")
                if proposal.get("act"):
                    yield _sse_event("evolve_thinking", {
                        "agent": agent_name,
                        "question": f"{agent_name} 提案: {proposal.get('action', '?')}",
                        "factors": [
                            f"意图: {proposal.get('intent', '')}",
                            f"目标: {proposal.get('target', '')}",
                        ],
                    })
                else:
                    yield _sse_event("evolve_thinking", {
                        "agent": agent_name,
                        "question": f"{agent_name} 选择不行动",
                        "factors": [proposal.get("reason", "")],
                    })

            # Step 2: 导演裁决
            acting_count = sum(1 for p in proposals if p.get("act"))
            yield _sse_event("evolve_thinking", {
                "agent": "天道",
                "question": f"裁决 {len(proposals)} 个角色提案（{acting_count} 个行动 / {len(proposals) - acting_count} 个观望）",
                "factors": [p["agent"] + (": " + p.get("action", "观望"))[:30] for p in proposals],
            })

            try:
                decision = director_agent.adjudicate(proposals, branch, enriched_goal)
            except Exception:
                logger.error("导演裁决失败，直接采纳提案:\n%s", traceback.format_exc())
                decision = director_agent._adopt_all_proposals(proposals)

            action_plan = {"actions": decision.actions, "model_name": decision.model_name}
            logger.info(
                "天道裁决完成: actions=%d, notes=%d, title=%s",
                len(decision.actions),
                len(decision.adjudication_notes),
                decision.event_title[:40] if decision.event_title else "(无)",
            )

        else:
            # ═══ 传统模式 ═══
            candidate_agent_names = [a["display_name"] for a in agents if a.get("can_act")][:4]
            thinking_factors = []
            if constraints:
                thinking_factors.append(f"用户约束: {'; '.join(constraints[:3])}")
            if branch.pending_variables:
                thinking_factors.append(f"待处理变量: {len(branch.pending_variables)} 条")

            yield _sse_event("evolve_thinking", {
                "agent": candidate_agent_names[0] if candidate_agent_names else "system",
                "question": f"第 {branch.current_step + 1} 步：哪些角色应该在此刻做出决策？",
                "factors": thinking_factors or ["基于角色驱动力和当前世界状态评估"],
                "candidates": candidate_agent_names,
            })

            try:
                action_plan = auto_action_service.generate_actions(
                    branch, agents, enriched_goal, memory_hints, action_views,
                )
            except Exception:
                action_plan = {"actions": [], "model_name": ""}

        # ═══ 执行（两种模式共用） ═══

        # Build display_name → agent_id lookup for robust resolution
        agent_id_lookup: Dict[str, str] = {}
        for a in agents:
            agent_id_lookup[a["agent_id"]] = a["agent_id"]
            agent_id_lookup[a["display_name"]] = a["agent_id"]
            if a.get("source_ref"):
                agent_id_lookup[a["source_ref"]] = a["agent_id"]

        queued_actions = []
        for action in action_plan["actions"]:
            ref = action["agent_ref"]
            resolved_id = agent_id_lookup.get(ref, ref)
            try:
                worldline_engine.queue_action(
                    session_id=session_id,
                    actor=resolved_id,
                    action=action["action"],
                    intent=action.get("intent", ""),
                    target=action.get("target", ""),
                    project_id=project_id,
                    graph_id=graph_id,
                    branch_id=branch_id,
                )
                queued_actions.append(action)
            except ValueError:
                logger.warning("跳过无法解析的 agent_ref: %s (原始: %s)", resolved_id, ref)

        step_kwargs: Dict[str, Any] = {}
        if decision and decision.event_title:
            step_kwargs["override_title"] = decision.event_title
        if decision and decision.event_summary:
            step_kwargs["override_summary"] = decision.event_summary

        session = worldline_engine.step(
            session_id=session_id,
            project_id=project_id,
            graph_id=graph_id,
            branch_id=branch_id,
            steps=1,
            event_status="candidate",
            **step_kwargs,
        )
        branch = require_branch(session, branch_id)
        completed_steps += 1

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

        try:
            goal_verdict = auto_action_service.evaluate_goal(branch, goal_text)
        except Exception:
            goal_verdict = auto_action_service.empty_goal_verdict(goal_text)

        if queued_actions:
            consecutive_empty = 0
        else:
            consecutive_empty += 1

        logger.info(
            "步骤 %d/%d 完成: actions=%d, consecutive_empty=%d, goal_reached=%s",
            completed_steps, resolved_steps,
            len(action_plan["actions"]),
            consecutive_empty,
            goal_verdict.get("goal_reached", False),
        )

        reason = stop_reason(completed_steps, resolved_steps, branch, queued_actions, goal_verdict, consecutive_empty)
        if reason:
            logger.info("推演停止: reason=%s", reason)
            break

    logger.info(
        "推演结束: completed_steps=%d/%d, stop_reason=%s, candidates=%d",
        completed_steps, resolved_steps, reason or "max_steps", len(candidate_events),
    )

    yield _sse_event("evolve_done", {
        "candidate_count": len(candidate_events),
        "completed_steps": completed_steps,
        "stop_reason": reason or "max_steps",
        "goal_verdict": goal_verdict,
    })

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
