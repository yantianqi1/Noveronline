"""写作检索规划员（Phase 0）。

在 orchestrator AgentLoop 启动前，单次调用一个轻量 LLM 让它先想清楚
「正式写作前应该先调用哪些工具」，输出 JSON 计划。计划随后被注入到
orchestrator 的 user_msg 顶端作为 ``<retrieval_plan>`` 块，作为最低检索基线。

按 CLAUDE.md「失败显式」原则：未绑定 ``writer_retrieval_planner`` 模块时
直接抛错向上传递；不做 silent fallback。
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

        Raises:
            ValueError: 当 ``writer_retrieval_planner`` 模块未在全局 LLM 设施
                面板绑定时（来自 LlmRouter.build_client）。
            RuntimeError: 当 LLM 返回非对象或缺少关键字段。
        """
        client = self.router.build_client(self.MODULE_KEY)
        system_prompt = build_retrieval_planner_prompt(task_type, context)
        user_payload = json.dumps(context, ensure_ascii=False, indent=2)
        result = client.chat_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        if not isinstance(result, dict):
            raise RuntimeError(
                f"writer_retrieval_planner 返回非对象: {type(result).__name__}"
            )
        calls = result.get("calls")
        if not isinstance(calls, list):
            raise RuntimeError("writer_retrieval_planner 返回缺少 calls 数组")
        return result

    @staticmethod
    def render_for_user_message(plan: dict[str, Any]) -> str:
        """把 plan dict 渲染成可读的中文清单，供注入到 user message。"""
        rationale = plan.get("rationale") or ""
        calls = plan.get("calls") or []
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
