"""世界线导演 Agent — ReACT 循环核心。

借鉴 MiroFish ReportAgent 的 ReACT 模式：
规划 → 工具调用 → 观察 → 综合裁决。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .llm_router import LlmRouter
from .worldline_director_prompts import (
    ADJUDICATE_SYSTEM_PROMPT,
    ADJUDICATE_USER_PROMPT,
    DIRECTOR_STEP_PROMPT,
    DIRECTOR_SYSTEM_PROMPT,
    FORCE_FINAL_MSG,
    INSUFFICIENT_TOOLS_MSG,
    OBSERVATION_TEMPLATE,
    TOOLS_DESCRIPTION_BLOCK,
    UNUSED_TOOLS_HINT,
)
from .worldline_director_tools import VALID_TOOL_NAMES, DirectorToolExecutor

logger = logging.getLogger(__name__)

DIRECTOR_MODULE_KEY = "worldline_director"
DIRECTOR_TEMPERATURE = 0.5
DIRECTOR_MAX_TOKENS = 1500
MAX_TOOL_CALLS = 4
MIN_TOOL_CALLS = 1
MAX_ITERATIONS = 6
MAX_ACTIONS_PER_STEP = 2
RECENT_EVENT_LIMIT = 4
CANDIDATE_LIMIT = 6


ADJUDICATE_TEMPERATURE = 0.3
ADJUDICATE_MAX_TOKENS = 1200


@dataclass
class DirectorDecision:
    """导演单步决策结果。"""

    narrative_intent: str = ""
    actions: List[Dict[str, str]] = field(default_factory=list)
    event_title: str = ""
    event_summary: str = ""
    director_note: str = ""
    adjudication_notes: List[Dict[str, str]] = field(default_factory=list)
    interviews: List[Dict[str, Any]] = field(default_factory=list)
    tool_calls_log: List[Dict[str, Any]] = field(default_factory=list)
    model_name: str = ""


class WorldlineDirectorAgent:
    """ReACT-based director agent for worldline evolution."""

    def __init__(
        self,
        llm_router: LlmRouter,
        tool_executor: DirectorToolExecutor,
    ):
        self.llm_router = llm_router
        self.tool_executor = tool_executor

    # ── 天道裁决模式 ──────────────────────────────────────────

    def adjudicate(
        self,
        proposals: List[Dict[str, Any]],
        branch,
        goal_text: str,
    ) -> DirectorDecision:
        """裁决角色提案：检查冲突、合理性，输出最终动作和叙事。

        This is the "天道" mode — characters propose, director only adjudicates.
        """
        try:
            client = self.llm_router.build_client(DIRECTOR_MODULE_KEY)
        except ValueError:
            logger.warning("%s 未绑定模型，直接采纳所有提案", DIRECTOR_MODULE_KEY)
            return self._adopt_all_proposals(proposals)

        # Build proposals text
        proposal_lines = []
        for p in proposals:
            if p.get("act"):
                proposal_lines.append(
                    f"- {p['agent']}（驱动: {p.get('drive', '?')}）提案行动：\n"
                    f"  动作: {p.get('action', '')}\n"
                    f"  意图: {p.get('intent', '')}\n"
                    f"  目标: {p.get('target', '')}\n"
                    f"  理由: {p.get('reason', '')}"
                )
            else:
                proposal_lines.append(
                    f"- {p['agent']}（驱动: {p.get('drive', '?')}）选择不行动。\n"
                    f"  理由: {p.get('reason', '无明确理由')}"
                )

        recent_events = []
        for evt in (branch.timeline or [])[-RECENT_EVENT_LIMIT:]:
            title = getattr(evt, "title", "") or "事件"
            summary = getattr(evt, "summary", "") or ""
            recent_events.append(f"- {title}: {summary[:120]}")

        user_prompt = ADJUDICATE_USER_PROMPT.format(
            branch_title=branch.title,
            current_step=branch.current_step,
            core_change=branch.core_change,
            goal_text=goal_text.strip() or "未设置",
            recent_events="\n".join(recent_events) if recent_events else "- 暂无",
            proposals_text="\n".join(proposal_lines) if proposal_lines else "- 所有角色选择不行动",
        )

        raw = client.chat_json(
            messages=[
                {"role": "system", "content": ADJUDICATE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=ADJUDICATE_TEMPERATURE,
            max_tokens=ADJUDICATE_MAX_TOKENS,
        )
        if not isinstance(raw, dict):
            logger.warning("导演裁决返回非 JSON，直接采纳提案")
            return self._adopt_all_proposals(proposals)

        # Parse actions
        actions = raw.get("actions", [])
        if not isinstance(actions, list):
            actions = []
        normalized = []
        for act in actions[:MAX_ACTIONS_PER_STEP]:
            if not isinstance(act, dict):
                continue
            agent_ref = str(act.get("agent_ref") or act.get("agent_id") or act.get("actor") or "").strip()
            action_text = str(act.get("action", "")).strip()
            if agent_ref and action_text:
                normalized.append({
                    "agent_ref": agent_ref,
                    "action": action_text,
                    "intent": str(act.get("intent", "")).strip(),
                    "target": str(act.get("target", "")).strip(),
                })

        # Parse adjudication notes
        notes = raw.get("adjudication_notes", [])
        if not isinstance(notes, list):
            notes = []

        return DirectorDecision(
            actions=normalized,
            event_title=str(raw.get("event_title", "")).strip(),
            event_summary=str(raw.get("event_summary", "")).strip(),
            adjudication_notes=notes,
            model_name=client.model,
        )

    def _adopt_all_proposals(self, proposals: List[Dict[str, Any]]) -> DirectorDecision:
        """Fallback: adopt all acting proposals without LLM adjudication."""
        actions = []
        for p in proposals:
            if p.get("act") and p.get("action"):
                actions.append({
                    "agent_ref": p["agent"],
                    "action": p["action"],
                    "intent": p.get("intent", ""),
                    "target": p.get("target", ""),
                })
        return DirectorDecision(
            actions=actions[:MAX_ACTIONS_PER_STEP],
            event_title="角色自主行动",
            event_summary="；".join(f"{a['agent_ref']}执行「{a['action']}」" for a in actions) or "世界保持平静",
        )

    # ── ReACT 导演模式（保留） ────────────────────────────────

    def direct_step(
        self,
        branch,
        session,
        agents: List[Dict[str, Any]],
        goal_text: str,
        memory_hints: Dict[str, str],
        action_views: Dict[str, Dict[str, Any]],
        container_dir: str,
        on_thinking: Optional[Callable] = None,
        on_interview: Optional[Callable] = None,
    ) -> DirectorDecision:
        """Execute one director step using ReACT loop.

        Returns a DirectorDecision with actions and narrative.
        """
        try:
            client = self.llm_router.build_client(DIRECTOR_MODULE_KEY)
        except ValueError:
            logger.warning("%s 未绑定模型，回退到空决策", DIRECTOR_MODULE_KEY)
            return DirectorDecision()

        messages = _build_initial_messages(branch, agents, goal_text, action_views)

        tool_calls_count = 0
        used_tools: set[str] = set()
        interviews: list[dict] = []
        tool_calls_log: list[dict] = []

        for iteration in range(MAX_ITERATIONS):
            response = client.chat(
                messages=messages,
                temperature=DIRECTOR_TEMPERATURE,
                max_tokens=DIRECTOR_MAX_TOKENS,
            )

            parsed_tools = _parse_tool_calls(response)
            has_final = "Final Answer:" in response

            # Conflict: both tool call and Final Answer — prefer tool.
            if parsed_tools and has_final:
                has_final = False

            # ── Final Answer ───────────────────────────────────
            if has_final:
                if tool_calls_count < MIN_TOOL_CALLS:
                    messages.append({
                        "role": "user",
                        "content": INSUFFICIENT_TOOLS_MSG.format(min_tool_calls=MIN_TOOL_CALLS),
                    })
                    continue
                decision = _parse_final_answer(response, client.model)
                decision.interviews = interviews
                decision.tool_calls_log = tool_calls_log
                return decision

            # ── Tool call ──────────────────────────────────────
            if parsed_tools:
                if tool_calls_count >= MAX_TOOL_CALLS:
                    messages.append({"role": "user", "content": FORCE_FINAL_MSG})
                    continue

                call = parsed_tools[0]
                tool_name = call.get("name", "")
                params = call.get("parameters", {})

                result = self.tool_executor.execute(
                    tool_name, params,
                    branch, session, agents, memory_hints, action_views, container_dir,
                )
                tool_calls_count += 1
                used_tools.add(tool_name)
                tool_calls_log.append({"tool": tool_name, "parameters": params, "result_length": len(result)})

                # Track interviews
                if tool_name == "interview_character":
                    char_name = params.get("character_name", "")
                    interviews.append({"character": char_name, "question": params.get("question", ""), "reply": result})
                    if on_interview:
                        on_interview(char_name, result)
                elif on_thinking:
                    on_thinking(tool_name, params)

                messages.append({"role": "assistant", "content": response})
                messages.append({
                    "role": "user",
                    "content": _observation_text(call, result, tool_calls_count, used_tools),
                })
                continue

            # ── No tool, no Final Answer ───────────────────────
            if tool_calls_count >= MIN_TOOL_CALLS:
                decision = _parse_plain_response(response, client.model)
                decision.interviews = interviews
                decision.tool_calls_log = tool_calls_log
                return decision

            messages.append({
                "role": "user",
                "content": "请调用工具观察局势，或以 \"Final Answer:\" 开头输出最终裁决。",
            })

        # ── Force final ────────────────────────────────────────
        messages.append({"role": "user", "content": FORCE_FINAL_MSG})
        response = client.chat(
            messages=messages,
            temperature=DIRECTOR_TEMPERATURE,
            max_tokens=DIRECTOR_MAX_TOKENS,
        )
        decision = _parse_final_answer(response, client.model)
        decision.interviews = interviews
        decision.tool_calls_log = tool_calls_log
        return decision


# ── Message building ───────────────────────────────────────────

def _build_initial_messages(
    branch, agents: List[Dict[str, Any]], goal_text: str, action_views: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    system_prompt = DIRECTOR_SYSTEM_PROMPT.format(tools_description=TOOLS_DESCRIPTION_BLOCK)

    # Build candidate agent lines
    actable = [a for a in agents if a.get("can_act")]
    actable.sort(key=lambda a: (1 if a.get("last_action_at") else 0, a.get("last_action_at") or ""))
    candidates = actable[:CANDIDATE_LIMIT]

    candidate_lines = []
    for agent in candidates:
        line = (
            f"- {agent['display_name']} | "
            f"种类={agent.get('agent_kind', '?')} | "
            f"驱动={agent.get('drive', '?')} | "
            f"张力={agent.get('tension', '?')} | "
            f"最近行动={agent.get('last_action_at') or '从未'}"
        )
        av = action_views.get(agent.get("agent_id", ""), {})
        if av.get("public_profile"):
            profile = av["public_profile"]
            if isinstance(profile, dict):
                identity = profile.get("identity", "")
                if identity:
                    line += f" | 身份={identity[:60]}"
            elif isinstance(profile, str):
                line += f" | 档案={profile[:60]}"
        candidate_lines.append(line)

    # Recent events
    events = branch.timeline[-RECENT_EVENT_LIMIT:] if branch.timeline else []
    event_lines = []
    for evt in events:
        title = getattr(evt, "title", "") or "事件"
        summary = getattr(evt, "summary", "") or ""
        event_lines.append(f"- {title}: {summary[:120]}")

    # Pending variables
    var_lines = [f"- {v.name}: {v.description}" for v in (branch.pending_variables or [])[:3]]

    user_prompt = DIRECTOR_STEP_PROMPT.format(
        branch_title=branch.title,
        current_step=branch.current_step,
        core_change=branch.core_change,
        goal_text=goal_text.strip() or "未设置创作目标",
        recent_events="\n".join(event_lines) if event_lines else "- 暂无",
        pending_variables="\n".join(var_lines) if var_lines else "- 暂无",
        candidate_agents="\n".join(candidate_lines) if candidate_lines else "- 暂无可行动角色",
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


# ── Tool call parsing (3 formats, from MiroFish ReportAgent) ──

def _parse_tool_calls(response: str) -> List[Dict[str, Any]]:
    """Parse tool calls from LLM response. Supports XML tags, bare JSON, trailing JSON."""
    calls: List[Dict[str, Any]] = []

    # Format 1: XML tags
    xml_pattern = r"<tool_call>\s*(\{.*?\})\s*</tool_call>"
    for match in re.finditer(xml_pattern, response, re.DOTALL):
        try:
            data = json.loads(match.group(1))
            if _is_valid_tool_call(data):
                calls.append(data)
        except (json.JSONDecodeError, ValueError):
            pass
    if calls:
        return calls

    # Format 2: Bare JSON
    stripped = response.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        try:
            data = json.loads(stripped)
            if _is_valid_tool_call(data):
                return [data]
        except (json.JSONDecodeError, ValueError):
            pass

    # Format 3: Trailing JSON object
    json_pattern = r'(\{"(?:name|tool)"\s*:.*?\})\s*$'
    match = re.search(json_pattern, stripped, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if _is_valid_tool_call(data):
                return [data]
        except (json.JSONDecodeError, ValueError):
            pass

    return []


def _is_valid_tool_call(data: dict) -> bool:
    tool_name = data.get("name") or data.get("tool")
    if tool_name and tool_name in VALID_TOOL_NAMES:
        if "tool" in data:
            data["name"] = data.pop("tool")
        if "params" in data and "parameters" not in data:
            data["parameters"] = data.pop("params")
        if "parameters" not in data:
            data["parameters"] = {}
        return True
    return False


# ── Observation formatting ─────────────────────────────────────

def _observation_text(call: Dict[str, Any], result: str, tool_calls_count: int, used_tools: set) -> str:
    all_tools = {"inspect_world_state", "interview_character", "check_relationships", "review_narrative_arc"}
    unused = all_tools - used_tools
    unused_hint = UNUSED_TOOLS_HINT.format(unused_list=", ".join(sorted(unused))) if unused else ""

    return OBSERVATION_TEMPLATE.format(
        tool_name=call.get("name", "?"),
        result=result[:3000],
        tool_calls_count=tool_calls_count,
        max_tool_calls=MAX_TOOL_CALLS,
        used_tools_str=", ".join(sorted(used_tools)),
        unused_hint=unused_hint,
    )


# ── Final Answer parsing ──────────────────────────────────────

def _parse_final_answer(response: str, model_name: str) -> DirectorDecision:
    """Extract DirectorDecision from Final Answer JSON."""
    marker = "Final Answer:"
    idx = response.find(marker)
    if idx < 0:
        return _parse_plain_response(response, model_name)

    raw = response[idx + len(marker):].strip()

    # Try to extract JSON from the raw text
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        return DirectorDecision(
            event_summary=raw[:500],
            model_name=model_name,
        )

    try:
        data = json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return DirectorDecision(
            event_summary=raw[:500],
            model_name=model_name,
        )

    actions = data.get("actions", [])
    if not isinstance(actions, list):
        actions = []
    # Normalize and limit actions
    normalized = []
    for act in actions[:MAX_ACTIONS_PER_STEP]:
        if not isinstance(act, dict):
            continue
        agent_ref = str(act.get("agent_ref") or act.get("agent_id") or act.get("actor") or "").strip()
        action_text = str(act.get("action", "")).strip()
        if agent_ref and action_text:
            normalized.append({
                "agent_ref": agent_ref,
                "action": action_text,
                "intent": str(act.get("intent", "")).strip(),
                "target": str(act.get("target", "")).strip(),
            })

    return DirectorDecision(
        narrative_intent=str(data.get("narrative_intent", "")).strip(),
        actions=normalized,
        event_title=str(data.get("event_title", "")).strip(),
        event_summary=str(data.get("event_summary", "")).strip(),
        director_note=str(data.get("director_note", "")).strip(),
        model_name=model_name,
    )


def _parse_plain_response(response: str, model_name: str) -> DirectorDecision:
    """Fallback: treat entire response as event summary."""
    # Remove any tool call remnants
    clean = re.sub(r"<tool_call>.*?</tool_call>", "", response, flags=re.DOTALL).strip()
    return DirectorDecision(
        event_summary=clean[:500],
        model_name=model_name,
    )
