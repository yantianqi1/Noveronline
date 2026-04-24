"""Base class for one-click runners.

A one-click runner wraps a single ``AgentLoop.run()`` iteration with:
- a hard-coded system prompt (specialised per button);
- a whitelist of tool schemas (read + one ``propose_*``) that excludes every
  real write tool; the ``_PROPOSE_TOOL_NAMES`` set in ``agent_loop`` keeps
  proposal execution on the read-parallel lane;
- passthrough of all SSE events, plus collection of ``tool_result.render``
  payloads into a final summary event so the API endpoint (and any future
  audit log) can see the cards that were drafted.

Runners never mutate DB state — the agent only draws proposal cards, and
the frontend adopts them via existing API clients (see §2.9).
"""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from ..agent_loop import AgentLoop
from ..tools import ASSET_TOOLS, BOOK_RUN_TOOLS, MANUSCRIPT_TOOLS, NOVEL_TOOLS, UNIFIED_TOOLS

logger = logging.getLogger(__name__)

_TOOLS_BY_NAME: dict[str, dict] = {
    t["function"]["name"]: t
    for t in (
        *NOVEL_TOOLS,
        *ASSET_TOOLS,
        *UNIFIED_TOOLS,
        *MANUSCRIPT_TOOLS,
        *BOOK_RUN_TOOLS,
    )
}


def filter_tools(names: list[str]) -> list[dict]:
    """Return OpenAI tool schemas whose function.name is in ``names``.

    Raises ``KeyError`` if any requested tool is unknown — fail loudly so
    typos in a runner's whitelist don't silently strip tools.
    """
    missing = [n for n in names if n not in _TOOLS_BY_NAME]
    if missing:
        raise KeyError(f"Unknown tool names in whitelist: {missing}")
    return [_TOOLS_BY_NAME[n] for n in names]


@dataclass
class OneClickResult:
    """Final accumulated state from one runner invocation."""

    runner: str
    verdict: str = ""
    cards: list[dict] = field(default_factory=list)
    rounds: int = 0
    elapsed_ms: int = 0
    error: str | None = None


class OneClickRunner:
    """Base class — subclasses provide name/prompt/tools/user_msg/max_rounds."""

    name: str = "one_click"
    max_rounds: int = 6

    def __init__(self, llm_router=None):
        from ...llm_router import LlmRouter

        self.router = llm_router or LlmRouter()

    # ---- subclass hooks ----
    def build_system_prompt(self, context: dict) -> str:
        raise NotImplementedError

    def build_user_message(self, context: dict) -> str:
        raise NotImplementedError

    def tool_names(self) -> list[str]:
        raise NotImplementedError

    # ---- runner entry ----
    async def run(self, context: dict) -> AsyncIterator[dict[str, Any]]:
        """Yield SSE events. Always emits a final ``summary`` event.

        Context must contain ``project_id``. Other keys are runner-specific
        (``chapter_id``, ``chapter_order``, ``target_word_count`` …) and are
        interpolated into the system prompt / user message.
        """
        project_id = context.get("project_id") or ""
        if not project_id:
            yield {"type": "error", "message": "缺少 project_id"}
            return

        t0 = time.monotonic()
        result = OneClickResult(runner=self.name)

        yield {
            "type": "start",
            "runner": self.name,
            "project_id": project_id,
            "ts": time.strftime("%H:%M:%S"),
        }

        try:
            system_prompt = self.build_system_prompt(context)
            user_msg = self.build_user_message(context)
            tools = filter_tools(self.tool_names())
        except KeyError as exc:
            result.error = f"工具白名单配置错误: {exc}"
            yield {"type": "error", "message": result.error}
            yield {"type": "summary", "runner": self.name, **_summary_payload(result, t0)}
            return

        try:
            client = await self.router.build_async_client("writer_orchestrator")
        except Exception as exc:
            logger.exception("OneClick runner %s failed to build LLM client", self.name)
            result.error = f"构建 LLM 客户端失败: {exc}"
            yield {"type": "error", "message": result.error}
            yield {"type": "summary", "runner": self.name, **_summary_payload(result, t0)}
            return

        loop = AgentLoop(
            llm_client=client,
            tools=tools,
            system_prompt=system_prompt,
            project_id=project_id,
            t0=t0,
        )
        loop.MAX_ROUNDS = self.max_rounds  # per-runner cap

        try:
            async for event in loop.run(user_msg):
                etype = event.get("type")
                if etype == "tool_result":
                    render = event.get("render")
                    if isinstance(render, dict) and render.get("type"):
                        # Preserve render card for the final summary.
                        result.cards.append(render)
                if etype == "brief_ready":
                    result.verdict = event.get("content") or ""
                if isinstance(event.get("round"), int):
                    result.rounds = max(result.rounds, event["round"] + 1)
                yield event
        except Exception as exc:
            logger.exception("OneClick runner %s agent loop failed", self.name)
            result.error = f"agent loop 执行失败: {exc}"
            yield {"type": "error", "message": result.error}

        yield {"type": "summary", "runner": self.name, **_summary_payload(result, t0)}


def _summary_payload(result: OneClickResult, t0: float) -> dict[str, Any]:
    result.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return {
        "verdict": result.verdict,
        "card_count": len(result.cards),
        "cards": result.cards,
        "rounds": result.rounds,
        "elapsed_ms": result.elapsed_ms,
        "error": result.error,
    }
