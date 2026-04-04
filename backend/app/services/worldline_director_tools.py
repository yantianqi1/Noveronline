"""世界线导演 Agent — 工具定义与执行。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .worldline_director_prompts import (
    INTERVIEW_CONTEXT_PROMPT,
    TOOL_DESC_ARC,
    TOOL_DESC_INSPECT,
    TOOL_DESC_INTERVIEW,
    TOOL_DESC_RELATIONSHIPS,
)

VALID_TOOL_NAMES = {"inspect_world_state", "interview_character", "check_relationships", "review_narrative_arc"}

DIRECTOR_TOOLS = {
    "inspect_world_state": {
        "name": "inspect_world_state",
        "description": TOOL_DESC_INSPECT,
        "parameters": {"focus": "聚焦方面（角色/关系/变量/全部）"},
    },
    "interview_character": {
        "name": "interview_character",
        "description": TOOL_DESC_INTERVIEW,
        "parameters": {"character_name": "角色名", "question": "导演提问"},
    },
    "check_relationships": {
        "name": "check_relationships",
        "description": TOOL_DESC_RELATIONSHIPS,
        "parameters": {"character_a": "角色A", "character_b": "角色B"},
    },
    "review_narrative_arc": {
        "name": "review_narrative_arc",
        "description": TOOL_DESC_ARC,
        "parameters": {},
    },
}

RECENT_EVENTS_FOR_INTERVIEW = 4


class DirectorToolExecutor:
    """Executes director tools against worldline state."""

    def __init__(self, character_agent_service, prepare_service=None):
        self.character_service = character_agent_service
        self.prepare_service = prepare_service

    def execute(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        branch,
        session,
        agents: List[Dict[str, Any]],
        memory_hints: Dict[str, str],
        action_views: Dict[str, Dict[str, Any]],
        container_dir: str,
    ) -> str:
        if tool_name == "inspect_world_state":
            return self._inspect_world_state(branch, agents, parameters.get("focus", "全部"))
        if tool_name == "interview_character":
            return self._interview_character(
                parameters.get("character_name", ""),
                parameters.get("question", ""),
                branch, session, agents, memory_hints, action_views, container_dir,
            )
        if tool_name == "check_relationships":
            return self._check_relationships(
                branch, parameters.get("character_a", ""), parameters.get("character_b", ""),
            )
        if tool_name == "review_narrative_arc":
            return self._review_narrative_arc(branch)
        return f"未知工具: {tool_name}"

    # ── inspect_world_state ────────────────────────────────────

    def _inspect_world_state(self, branch, agents: List[Dict[str, Any]], focus: str) -> str:
        sections = []

        if focus in ("角色", "全部"):
            agent_lines = []
            for agent in agents:
                if not agent.get("can_act"):
                    continue
                line = (
                    f"- {agent['display_name']} | "
                    f"种类={agent.get('agent_kind', '?')} | "
                    f"驱动={agent.get('drive', '?')} | "
                    f"张力={agent.get('tension', '?')} | "
                    f"状态={agent.get('status', '?')} | "
                    f"最近行动={agent.get('last_action_at') or '从未行动'}"
                )
                agent_lines.append(line)
            sections.append("【可行动角色】\n" + ("\n".join(agent_lines) if agent_lines else "- 暂无"))

        if focus in ("关系", "全部"):
            rel_states = branch.relationship_states if isinstance(branch.relationship_states, list) else []
            rel_lines = []
            for rel in rel_states[:10]:
                if isinstance(rel, dict):
                    rel_lines.append(
                        f"- {rel.get('source', '?')} → {rel.get('target', '?')} | "
                        f"状态={rel.get('status', '?')} | "
                        f"变化={rel.get('change', '?')} | "
                        f"备注={rel.get('note', '')}"
                    )
            sections.append("【关系网络】\n" + ("\n".join(rel_lines) if rel_lines else "- 暂无关系数据"))

        if focus in ("变量", "全部"):
            var_lines = []
            for var in (branch.pending_variables or [])[:5]:
                var_lines.append(f"- {var.name}: {var.description}")
            act_lines = []
            for act in (branch.pending_actions or [])[:5]:
                act_lines.append(f"- {act.actor}: {act.action}")
            sections.append(
                f"【待处理变量 ({len(branch.pending_variables or [])})】\n"
                + ("\n".join(var_lines) if var_lines else "- 无") + "\n"
                + f"【待处理动作 ({len(branch.pending_actions or [])})】\n"
                + ("\n".join(act_lines) if act_lines else "- 无")
            )

        return "\n\n".join(sections)

    # ── interview_character ────────────────────────────────────

    def _interview_character(
        self,
        character_name: str,
        question: str,
        branch, session,
        agents: List[Dict[str, Any]],
        memory_hints: Dict[str, str],
        action_views: Dict[str, Dict[str, Any]],
        container_dir: str,
    ) -> str:
        # Find agent by name
        agent = None
        for a in agents:
            if a.get("display_name") == character_name:
                agent = a
                break
        if not agent:
            return f"找不到角色「{character_name}」。可用角色: {', '.join(a['display_name'] for a in agents if a.get('can_act'))}"

        # Build context
        actor_state = agent.get("state") or {}
        actor_state.setdefault("drive", agent.get("drive", ""))
        actor_state.setdefault("tension", agent.get("tension", ""))
        actor_state.setdefault("status", agent.get("status", ""))
        actor_state.setdefault("role", agent.get("role", ""))

        recent_events = []
        for evt in (branch.timeline or [])[-RECENT_EVENTS_FOR_INTERVIEW:]:
            recent_events.append({
                "title": getattr(evt, "title", "") or "",
                "summary": getattr(evt, "summary", "") or "",
            })

        branch_summary = {
            "title": branch.title,
            "core_change": branch.core_change,
        }

        # Build dossier context if prepare service available
        dossier_context = {}
        if self.prepare_service:
            try:
                dossier_context = self.prepare_service.build_dialogue_bundle(
                    container_dir, session, agent,
                )
            except Exception:
                pass

        # Build memory bundle (minimal)
        memory_bundle = {}
        hint = memory_hints.get(agent.get("agent_id", ""))
        if hint:
            memory_bundle["rendered_context"] = hint

        # Use character agent service to generate reply
        try:
            result = self.character_service.generate_reply(
                actor_name=character_name,
                actor_state=actor_state,
                message=question,
                recent_events=recent_events,
                branch_summary=branch_summary,
                mode="llm",
                memory_bundle=memory_bundle,
                dossier_context=dossier_context,
            )
            reply = result.get("reply", "")
            drive = result.get("drive", "")
            suggested = result.get("suggested_actions", [])
            parts = [f"【{character_name} 的回应】\n{reply}"]
            if drive:
                parts.append(f"当前驱动力: {drive}")
            if suggested:
                parts.append(f"建议行动: {'; '.join(suggested[:3])}")
            return "\n".join(parts)
        except Exception as exc:
            return f"采访 {character_name} 失败: {exc}"

    # ── check_relationships ────────────────────────────────────

    def _check_relationships(self, branch, char_a: str, char_b: str) -> str:
        rel_states = branch.relationship_states if isinstance(branch.relationship_states, list) else []
        found = []
        for rel in rel_states:
            if not isinstance(rel, dict):
                continue
            src = rel.get("source", "")
            tgt = rel.get("target", "")
            if (src == char_a and tgt == char_b) or (src == char_b and tgt == char_a):
                found.append(rel)

        if not found:
            return f"未找到 {char_a} 与 {char_b} 之间的关系记录。他们可能尚未产生直接关联。"

        lines = []
        for rel in found:
            lines.append(
                f"方向: {rel.get('source', '')} → {rel.get('target', '')}\n"
                f"状态: {rel.get('status', '未知')}\n"
                f"变化: {rel.get('change', '未知')}\n"
                f"备注: {rel.get('note', '')}\n"
                f"历史: {rel.get('history', '无')}\n"
                f"信任: {rel.get('trust_level', '未知')}\n"
                f"冲突触发: {rel.get('conflict_trigger', '未知')}"
            )
        return f"【{char_a} ↔ {char_b} 关系详情】\n" + "\n---\n".join(lines)

    # ── review_narrative_arc ───────────────────────────────────

    def _review_narrative_arc(self, branch) -> str:
        timeline = branch.timeline or []
        if not timeline:
            return "叙事弧线为空，世界线尚未开始推演。"

        lines = [f"【叙事弧线回顾 — 共 {len(timeline)} 步】\n"]
        for evt in timeline:
            step = getattr(evt, "step", "?")
            title = getattr(evt, "title", "")
            summary = getattr(evt, "summary", "")
            drivers = getattr(evt, "driving_entities", [])
            status = getattr(evt, "status", "canon")
            driver_text = ", ".join(drivers[:3]) if drivers else "系统"
            lines.append(f"第{step}步 [{status}] {title}\n  驱动: {driver_text}\n  {summary[:150]}")

        lines.append(f"\n当前步数: {branch.current_step}")
        lines.append(f"核心偏移: {branch.core_change}")
        return "\n".join(lines)
