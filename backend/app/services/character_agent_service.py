"""
世界线角色对话服务
根据角色当前状态、最近事件与用户输入，生成可继续推进剧情的本地回复。
"""

from typing import Any, Dict, List, Optional

from .llm_router import LlmRouter

TEMPLATE_MODE = "template"
LLM_MODE = "llm"
WORLDLINE_DIALOGUE_MODULE = "worldline_agent_dialogue"

WORLDLINE_AGENT_DIALOGUE_SYSTEM_PROMPT = """你是一名小说世界线中的角色扮演与关系推进助手。

你需要基于当前角色状态、最近事件和用户提问，用第一人称给出符合人物立场的简洁回复。
要求：
1. 不要脱离当前世界线设定。
2. 回复应体现角色目标、顾虑、当前张力。
3. 不要输出 JSON，只输出角色回复正文。
"""


class CharacterAgentService:
    def __init__(self, llm_router: Optional[LlmRouter] = None):
        self.llm_router = llm_router or LlmRouter()

    def generate_reply(
        self,
        actor_name: str,
        actor_state: Dict[str, Any],
        message: str,
        recent_events: List[Dict[str, Any]],
        branch_summary: Dict[str, Any],
        mode: str = TEMPLATE_MODE,
        memory_bundle: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if mode not in {TEMPLATE_MODE, LLM_MODE}:
            raise ValueError("mode 必须是 template 或 llm")
        role = actor_state.get("role") or actor_state.get("entity_role") or "角色"
        drive = actor_state.get("drive") or actor_state.get("core_drive") or "维持自己的目标"
        tension = actor_state.get("tension") or actor_state.get("hidden_tension") or "局势仍有未知风险"
        status = actor_state.get("status", "active")
        reply, model_name = self._build_reply(
            actor_name,
            actor_state,
            message,
            recent_events,
            branch_summary,
            mode,
            role,
            drive,
            tension,
            memory_bundle or {},
        )
        return {
            "agent": actor_name,
            "status": status,
            "drive": drive,
            "branch_title": branch_summary.get("title", ""),
            "reply": reply,
            "suggested_actions": self._suggest_actions(message, drive),
            "worldline_observation": f"{actor_name} 目前倾向于围绕“{drive}”继续行动。",
            "generator_mode": mode,
            "model_name": model_name,
            "memory_context": (memory_bundle or {}).get("rendered_context", ""),
        }

    def _build_reply(
        self,
        actor_name: str,
        actor_state: Dict[str, Any],
        message: str,
        recent_events: List[Dict[str, Any]],
        branch_summary: Dict[str, Any],
        mode: str,
        role: str,
        drive: str,
        tension: str,
        memory_bundle: Dict[str, Any],
    ) -> tuple[str, str]:
        if mode == TEMPLATE_MODE:
            return self._template_reply(actor_name, message, recent_events, role, drive, tension, memory_bundle), ""
        return self._llm_reply(actor_name, actor_state, message, recent_events, branch_summary, memory_bundle)

    def _template_reply(
        self,
        actor_name: str,
        message: str,
        recent_events: List[Dict[str, Any]],
        role: str,
        drive: str,
        tension: str,
        memory_bundle: Dict[str, Any],
    ) -> str:
        event_hint = "；".join(event.get("title", "") for event in recent_events[:2] if event.get("title")) or "局势仍在发酵"
        stance = self._infer_stance(message)
        memory_hint = self._memory_hint(memory_bundle)
        reply = (
            f"我是{actor_name}。以我现在作为“{role}”的处境来看，"
            f"我最优先的目标仍然是{drive}。你刚才提到“{message.strip()}”，"
            f"这件事在当前世界线里意味着{stance}。"
            f"最近的局面是：{event_hint}。"
            f"我最担心的是{tension}，所以我不会轻易把底牌全部交出去。"
        )
        return reply + (f" 我记得：{memory_hint}。" if memory_hint else "")

    def _llm_reply(
        self,
        actor_name: str,
        actor_state: Dict[str, Any],
        message: str,
        recent_events: List[Dict[str, Any]],
        branch_summary: Dict[str, Any],
        memory_bundle: Dict[str, Any],
    ) -> tuple[str, str]:
        try:
            client = self.llm_router.build_client(WORLDLINE_DIALOGUE_MODULE)
        except ValueError as exc:
            raise ValueError(f"{WORLDLINE_DIALOGUE_MODULE} 未绑定可用模型: {exc}") from exc
        prompt = self._llm_prompt(actor_name, actor_state, message, recent_events, branch_summary, memory_bundle)
        reply = client.chat(
            messages=[
                {"role": "system", "content": WORLDLINE_AGENT_DIALOGUE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=900,
        )
        return reply.strip(), client.model

    def _llm_prompt(
        self,
        actor_name: str,
        actor_state: Dict[str, Any],
        message: str,
        recent_events: List[Dict[str, Any]],
        branch_summary: Dict[str, Any],
        memory_bundle: Dict[str, Any],
    ) -> str:
        event_lines = [f"- {item.get('title', '未命名事件')}: {item.get('summary', '')}" for item in recent_events[:4]]
        return (
            f"角色名：{actor_name}\n"
            f"分支标题：{branch_summary.get('title', '')}\n"
            f"分支核心变化：{branch_summary.get('core_change', '')}\n"
            f"当前状态：{actor_state}\n"
            f"最近事件：\n{chr(10).join(event_lines) if event_lines else '- 暂无'}\n"
            f"记忆上下文：\n{memory_bundle.get('rendered_context', '- 暂无')}\n"
            f"用户消息：{message}\n"
            "请直接输出该角色的回复正文。"
        )

    def _memory_hint(self, memory_bundle: Dict[str, Any]) -> str:
        session_items = memory_bundle.get("session_memories") or []
        long_term_items = memory_bundle.get("long_term_memories") or []
        ordered = list(session_items) + list(long_term_items)
        ordered.sort(
            key=lambda item: (
                0 if item.get("memory_type") in {"strategy", "promise", "relationship", "goal", "preference"} else 1,
                -float(item.get("salience") or 0.0),
            ),
        )
        for item in ordered:
            summary = str(item.get("summary") or "").strip()
            if summary:
                return summary
        return ""

    def _infer_stance(self, message: str) -> str:
        if any(keyword in message for keyword in ("合作", "结盟", "联手", "帮助")):
            return "一次需要谨慎交换条件的合作试探"
        if any(keyword in message for keyword in ("杀", "攻击", "出手", "镇压", "夺取")):
            return "局势会迅速转向公开冲突"
        if any(keyword in message for keyword in ("调查", "真相", "线索", "证据")):
            return "情报链会被重新激活"
        return "它会改变我对同盟与敌意的判断顺序"

    def _suggest_actions(self, message: str, drive: str) -> List[str]:
        if any(keyword in message for keyword in ("合作", "结盟")):
            return ["先索要对方筹码", "安排一场试探性会面", f"把合作框架绑定到“{drive}”"]
        if any(keyword in message for keyword in ("调查", "线索", "真相")):
            return ["先验证消息来源", "寻找第二个证人", "避免在公开场合暴露调查方向"]
        return ["观察周围人的反应", "保留一条退路", f"继续围绕“{drive}”推进"]
