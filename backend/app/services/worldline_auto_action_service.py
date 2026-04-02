"""世界线自动演化动作与目标评估服务。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .llm_router import LlmRouter

WORLDLINE_AGENT_ACTION_MODULE = "worldline_agent_action"
WORLDLINE_GOAL_EVALUATOR_MODULE = "worldline_goal_evaluator"
ACTION_TEMPERATURE = 0.4
GOAL_TEMPERATURE = 0.2
ACTION_MAX_TOKENS = 1200
GOAL_MAX_TOKENS = 700
MAX_ACTIONS_PER_ROUND = 2
CANDIDATE_AGENT_LIMIT = 6
RECENT_EVENT_LIMIT = 4
PENDING_VARIABLE_LIMIT = 3

ACTION_SYSTEM_PROMPT = """你是一名小说世界线自动演化导演。

你需要基于当前分支状态，为本轮最应该出手的 agent 生成有限动作。
要求：
1. 只输出 JSON 对象。
2. actions 最多 2 条。
3. 尽量让最近较少行动的 agent 轮流推动剧情。
4. 动作必须贴合角色目标、张力和最近事件。
5. 如果当前不适合新增动作，返回空数组。
"""

GOAL_SYSTEM_PROMPT = """你是一名小说世界线目标裁判。

你需要判断给定分支是否已经满足创作者的自然语言最终条件。
要求：
1. 只输出 JSON 对象。
2. 不要生成新剧情，只根据现有状态判断。
3. confidence 取 0 到 1 之间的小数。
"""


def _event_title(event: Any) -> str:
    return getattr(event, "title", "") or "未命名事件"


def _event_summary(event: Any) -> str:
    return getattr(event, "summary", "") or ""


def _sorted_candidates(agents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    actable = [item for item in agents if item.get("can_act")]
    return sorted(
        actable,
        key=lambda item: (
            1 if item.get("last_action_at") else 0,
            item.get("last_action_at") or "",
            item.get("display_name") or "",
        ),
    )[:CANDIDATE_AGENT_LIMIT]


class WorldlineAutoActionService:
    def __init__(self, llm_router: Optional[LlmRouter] = None):
        self.llm_router = llm_router or LlmRouter()

    def empty_goal_verdict(self, goal_text: str = "") -> Dict[str, Any]:
        reason = "未设置最终条件" if not goal_text.strip() else "目标尚未达成"
        return {
            "goal_reached": False,
            "reason": reason,
            "confidence": 0.0,
            "model_name": "",
        }

    def generate_actions(
        self,
        branch,
        agents: List[Dict[str, Any]],
        goal_text: str = "",
        memory_hints: Optional[Dict[str, str]] = None,
        action_views: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        client = self._build_client(WORLDLINE_AGENT_ACTION_MODULE)
        candidates = _sorted_candidates(agents)
        payload = client.chat_json_value(
            messages=self._action_messages(branch, candidates, goal_text, memory_hints or {}, action_views or {}),
            temperature=ACTION_TEMPERATURE,
            max_tokens=ACTION_MAX_TOKENS,
        )
        return {
            "actions": self._normalize_actions(self._action_items(payload), candidates),
            "model_name": client.model,
        }

    def evaluate_goal(self, branch, goal_text: str) -> Dict[str, Any]:
        if not goal_text.strip():
            return self.empty_goal_verdict(goal_text)
        client = self._build_client(WORLDLINE_GOAL_EVALUATOR_MODULE)
        payload = client.chat_json(
            messages=self._goal_messages(branch, goal_text),
            temperature=GOAL_TEMPERATURE,
            max_tokens=GOAL_MAX_TOKENS,
        )
        return self._normalize_goal_verdict(payload, client.model)

    def _build_client(self, module_key: str):
        try:
            return self.llm_router.build_client(module_key)
        except ValueError as exc:
            raise ValueError(f"{module_key} 未绑定可用模型: {exc}") from exc

    def _action_messages(
        self,
        branch,
        candidates: List[Dict[str, Any]],
        goal_text: str,
        memory_hints: Dict[str, str],
        action_views: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": ACTION_SYSTEM_PROMPT},
            {"role": "user", "content": self._action_prompt(branch, candidates, goal_text, memory_hints, action_views)},
        ]

    def _goal_messages(self, branch, goal_text: str) -> List[Dict[str, str]]:
        return [
            {"role": "system", "content": GOAL_SYSTEM_PROMPT},
            {"role": "user", "content": self._goal_prompt(branch, goal_text)},
        ]

    def _action_prompt(
        self,
        branch,
        candidates: List[Dict[str, Any]],
        goal_text: str,
        memory_hints: Dict[str, str],
        action_views: Dict[str, Dict[str, Any]],
    ) -> str:
        event_lines = self._recent_event_lines(branch)
        variable_lines = self._pending_variable_lines(branch)
        candidate_lines = self._candidate_lines(candidates, memory_hints, action_views)
        goal_line = goal_text.strip() or "未设置最终条件"
        return (
            f"分支标题：{branch.title}\n"
            f"当前步数：{branch.current_step}\n"
            f"分支核心变化：{branch.core_change}\n"
            f"创作目标：{goal_line}\n"
            f"最近事件：\n{event_lines}\n"
            f"待处理变量：\n{variable_lines}\n"
            f"候选 agent：\n{candidate_lines}\n"
            "请输出 JSON："
            '{"actions":[{"agent_id":"候选中的 display_name","action":"动作","intent":"动机","target":"目标"}]}'
        )

    def _goal_prompt(self, branch, goal_text: str) -> str:
        actor_lines = [
            f"- {name}: status={state.get('status', '')}, drive={state.get('drive') or state.get('core_drive', '')}, "
            f"last_action={state.get('last_action', '')}"
            for name, state in list(branch.actor_states.items())[:5]
        ]
        event_lines = self._recent_event_lines(branch)
        return (
            f"最终条件：{goal_text.strip()}\n"
            f"分支标题：{branch.title}\n"
            f"当前步数：{branch.current_step}\n"
            f"分支核心变化：{branch.core_change}\n"
            f"最近事件：\n{event_lines}\n"
            f"关键角色状态：\n{chr(10).join(actor_lines) if actor_lines else '- 暂无'}\n"
            '请输出 JSON：{"goal_reached":true/false,"reason":"判断原因","confidence":0.0}'
        )

    def _recent_event_lines(self, branch) -> str:
        events = branch.timeline[-RECENT_EVENT_LIMIT:]
        lines = [f"- {_event_title(item)}: {_event_summary(item)}" for item in events]
        return "\n".join(lines) if lines else "- 暂无"

    def _pending_variable_lines(self, branch) -> str:
        variables = branch.pending_variables[:PENDING_VARIABLE_LIMIT]
        lines = [f"- {item.name}: {item.description}" for item in variables]
        return "\n".join(lines) if lines else "- 暂无"

    def _candidate_lines(self, candidates: List[Dict[str, Any]], memory_hints: Dict[str, str], action_views: Dict[str, Dict[str, Any]]) -> str:
        lines = [
            (
                f"- {item['display_name']} | kind={item['agent_kind']} | drive={item['drive']} | "
                f"tension={item['tension']} | last_action_at={item.get('last_action_at') or 'never'}"
                + (f" | 记忆={memory_hints[item['agent_id']]}" if memory_hints.get(item["agent_id"]) else "")
                + (f" | 公开档案={action_views[item['agent_id']]['public_profile']}" if action_views.get(item["agent_id"], {}).get("public_profile") else "")
                + (f" | 关系视角={action_views[item['agent_id']]['relationship_view']}" if action_views.get(item["agent_id"], {}).get("relationship_view") else "")
            )
            for item in candidates
        ]
        return "\n".join(lines) if lines else "- 暂无可行动 agent"

    def _action_items(self, payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            raise ValueError("worldline_agent_action 返回格式错误：必须是 JSON 对象或动作数组")
        raw_actions = payload.get("actions", [])
        if not isinstance(raw_actions, list):
            raise ValueError("worldline_agent_action 返回格式错误：actions 必须是数组")
        return raw_actions

    def _normalize_actions(
        self,
        raw_actions: List[Dict[str, Any]],
        candidates: List[Dict[str, Any]],
    ) -> List[Dict[str, str]]:
        if not isinstance(raw_actions, list):
            raise ValueError("worldline_agent_action 返回格式错误：actions 必须是数组")
        lookup = self._agent_lookup(candidates)
        return self._valid_actions(raw_actions, lookup)

    def _agent_lookup(self, candidates: List[Dict[str, Any]]) -> Dict[str, str]:
        lookup: Dict[str, str] = {}
        for item in candidates:
            for key in (item.get("agent_id"), item.get("display_name"), item.get("source_ref")):
                text = str(key or "").strip()
                if text:
                    lookup[text] = item["display_name"]
        return lookup

    def _valid_actions(
        self,
        raw_actions: List[Dict[str, Any]],
        lookup: Dict[str, str],
    ) -> List[Dict[str, str]]:
        actions: List[Dict[str, str]] = []
        seen = set()
        for item in raw_actions:
            if len(actions) >= MAX_ACTIONS_PER_ROUND:
                break
            action = self._normalize_action_item(item, lookup, seen)
            if not action:
                continue
            actions.append(action)
            seen.add(action["agent_ref"])
        return actions

    def _normalize_action_item(
        self,
        item: Dict[str, Any],
        lookup: Dict[str, str],
        seen: set[str],
    ) -> Optional[Dict[str, str]]:
        if not isinstance(item, dict):
            return None
        raw_ref = str(item.get("agent_id") or item.get("agent_ref") or item.get("actor") or "").strip()
        action = str(item.get("action", "")).strip()
        if not raw_ref or not action or raw_ref not in lookup:
            return None
        resolved = lookup[raw_ref]
        if resolved in seen:
            return None
        return {
            "agent_ref": resolved,
            "action": action,
            "intent": str(item.get("intent", "")).strip(),
            "target": str(item.get("target", "")).strip(),
        }

    def _normalize_goal_verdict(self, payload: Dict[str, Any], model_name: str) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("worldline_goal_evaluator 返回格式错误：必须是 JSON 对象")
        confidence = payload.get("confidence", 0.0)
        try:
            numeric_confidence = float(confidence)
        except (TypeError, ValueError) as exc:
            raise ValueError("worldline_goal_evaluator 返回格式错误：confidence 必须是数字") from exc
        reason = str(payload.get("reason") or "").strip()
        goal_reached = bool(payload.get("goal_reached"))
        return {
            "goal_reached": goal_reached,
            "reason": reason or ("目标已达成" if goal_reached else "目标尚未达成"),
            "confidence": max(0.0, min(numeric_confidence, 1.0)),
            "model_name": model_name,
        }
