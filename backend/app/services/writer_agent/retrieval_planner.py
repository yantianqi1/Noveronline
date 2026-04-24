"""写作检索规划员（Phase 0）。

在 orchestrator AgentLoop 启动前，单次调用一个轻量 LLM 让它先想清楚
「正式写作前应该先调用哪些工具」，输出 JSON 计划。计划随后被注入到
orchestrator 的 user_msg 顶端作为 ``<retrieval_plan>`` 块，作为最低检索基线。

失败策略：若 ``writer_retrieval_planner`` 模块未绑定或 LLM 返回异常，
返回 ``{calls: [], degraded: True, error: "..."}`` 而非抛错。上层 orchestrator
感知到 degraded=True 后会 yield 一条 warning 事件但**继续执行** AgentLoop，
让 agent 依靠 system prompt 中的启发式规则自主检索。这样做的动机是：一个
可选的检索建议器不应让整个写作请求硬失败；agent 在没有计划时依然能完成
任务，只是可能会多调几轮工具。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .prompts import build_retrieval_planner_prompt

logger = logging.getLogger(__name__)


class RetrievalPlanner:
    MODULE_KEY = "writer_retrieval_planner"

    def __init__(self, llm_router=None) -> None:
        from ..llm_router import LlmRouter
        self.router = llm_router or LlmRouter()

    def plan(self, task_type: str, context: dict[str, Any]) -> dict[str, Any]:
        """单次 LLM 调用，返回 ``{rationale, calls: [...]}``。

        永不抛错：任何失败都降级为 ``{rationale, calls: [], degraded: True, error: ...}``。
        调用方通过 ``result.get("degraded")`` 判断是否需要警告用户。
        """
        try:
            client = self.router.build_client(self.MODULE_KEY)
        except ValueError as exc:
            logger.warning(
                "retrieval planner module not bound, degrading: %s", exc,
            )
            return {
                "rationale": "writer_retrieval_planner 模块未绑定",
                "calls": [],
                "degraded": True,
                "error": f"LLM 模块未绑定 (writer_retrieval_planner): {exc}",
            }

        system_prompt = build_retrieval_planner_prompt(task_type, context)
        user_payload = json.dumps(context, ensure_ascii=False, indent=2)
        try:
            result = client.chat_json(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_payload},
                ],
                temperature=0.1,
                max_tokens=800,
            )
        except Exception as exc:
            logger.warning("retrieval planner LLM call failed, degrading", exc_info=True)
            return {
                "rationale": "检索规划员调用失败",
                "calls": [],
                "degraded": True,
                "error": f"检索规划员 LLM 调用失败: {exc}",
            }

        if not isinstance(result, dict):
            return {
                "rationale": "检索规划员返回格式非法",
                "calls": [],
                "degraded": True,
                "error": f"writer_retrieval_planner 返回非对象: {type(result).__name__}",
            }
        calls = result.get("calls")
        if not isinstance(calls, list):
            return {
                "rationale": result.get("rationale") or "检索规划员返回缺少 calls",
                "calls": [],
                "degraded": True,
                "error": "writer_retrieval_planner 返回缺少 calls 数组",
            }
        return result

    @staticmethod
    def render_for_user_message(plan: dict[str, Any]) -> str:
        """把 plan dict 渲染成可读的中文清单，供注入到 user message。

        若 plan 为降级状态（degraded=True）或 calls 为空，返回空字符串——
        让 orchestrator 的 user message 不带 retrieval_plan 块，提示词里的
        "如果包含 <retrieval_plan>..." 子句自然失效，agent 依靠启发式规则工作。
        """
        calls = plan.get("calls") or []
        if not calls:
            return ""
        rationale = plan.get("rationale") or ""
        lines = ["<retrieval_plan>"]
        if rationale:
            lines.append(f"规划理由：{rationale}")
        lines.append(f"必须先调用的工具（共 {len(calls)} 项）：")
        for i, c in enumerate(calls, 1):
            tool = c.get("tool", "?")
            args = c.get("arguments") or {}
            reason = c.get("reason") or ""
            args_str = json.dumps(args, ensure_ascii=False)
            lines.append(f"  {i}. {tool}({args_str}) — {reason}")
        lines.append("</retrieval_plan>")
        return "\n".join(lines)
