"""✍️ 一键续写本章 — dual-track runner (§4.3, §4.4.2).

Phase 1: run ``AgentLoop`` with a tight whitelist (read tools + the single
``propose_prose_continuation`` tool) so the LLM gathers context and hands us
a ``writing_brief`` dict.

Phase 2: take the brief and drive ``WriterComposer.compose_stream`` to emit
``writer_token`` events; when streaming finishes, assemble a ``ProseDiffView``
card (variant ``source="splice_block"``, scope ``manuscript_block``) as the
final ``tool_result`` render so the user can adopt it into the chapter.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from ..agent_loop import AgentLoop
from .base import OneClickResult, filter_tools

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """你是小说写作 agent 的「章尾续写助手」。用户希望从当前章节最后一块 manuscript 的
末尾自然衔接一段 400–800 字的正文。你不直接写正文（写作由外层 WriterComposer 完成），
你的任务是检索设定、生成 writing_brief，然后只调一次 propose_prose_continuation
封装衔接位置。

执行顺序（必须）：
1. 调 get_manuscript_context(token_budget=6000) 拿最后一块 block_id + tail_text
   + 近 2 场景摘要 + POV/地点。
2. 调 query_entity(POV, section='profile') 拿说话风格。
3. 若 tail_text 末尾提及未解决悬念 → get_open_threads 核对。
4. 把检索成果组装到 propose_prose_continuation 的参数里，返回调用即终止。

严禁调用 manage_* / splice_block / rewrite_span / 任何 propose_ 以外的写类工具。
"""


_TOOL_WHITELIST = [
    "get_manuscript_context",
    "search_manuscript",
    "query_entity",
    "query_relationship",
    "get_open_threads",
    "get_character_voice",
    "search_settings",
    "propose_prose_continuation",
]


class ChapterContinuerRunner:
    """Dual-track runner: retrieval agent + streaming WriterComposer.

    Unlike the other OneClick runners we don't subclass ``OneClickRunner``
    because this one needs a bespoke pipeline (agent → intercept brief →
    streaming → card). The public surface (``name``, ``max_rounds``,
    ``run(context)``) stays compatible so the API endpoint can treat it
    uniformly.
    """

    name = "chapter_continuer"
    max_rounds = 5

    def __init__(self, llm_router=None):
        from ...llm_router import LlmRouter

        self.router = llm_router or LlmRouter()

    def build_system_prompt(self, context: dict) -> str:
        return _SYSTEM_PROMPT

    def build_user_message(self, context: dict) -> str:
        chapter_id = context.get("chapter_id") or ""
        chapter_order = context.get("chapter_order") or 0
        last_block = context.get("last_block_id") or ""
        target = context.get("target_word_count") or 600
        return (
            f"请为第 {chapter_order} 章（chapter_id={chapter_id}）做章尾续写。"
            f"目标字数 ≈ {target} 字。"
            f"{'锚点=' + last_block + '；' if last_block else ''}"
            "先 get_manuscript_context 拿最新 tail，再按系统提示执行，"
            "最后调一次 propose_prose_continuation。"
        )

    async def run(self, context: dict) -> AsyncIterator[dict[str, Any]]:
        project_id = context.get("project_id") or ""
        chapter_id = context.get("chapter_id") or ""
        if not project_id or not chapter_id:
            yield {"type": "error", "message": "缺少 project_id 或 chapter_id"}
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
            client = await self.router.build_async_client("writer_orchestrator")
        except Exception as exc:  # LLM not configured / upstream failure
            logger.exception("ChapterContinuer failed to build orchestrator client")
            result.error = f"构建 orchestrator 客户端失败: {exc}"
            yield {"type": "error", "message": result.error}
            yield {"type": "summary", "runner": self.name, **_summary(result, t0)}
            return

        tools = filter_tools(_TOOL_WHITELIST)
        loop = AgentLoop(
            llm_client=client,
            tools=tools,
            system_prompt=self.build_system_prompt(context),
            project_id=project_id,
            t0=t0,
        )
        loop.MAX_ROUNDS = self.max_rounds

        brief_payload: dict[str, Any] | None = None
        user_msg = self.build_user_message(context)

        try:
            async for event in loop.run(user_msg):
                etype = event.get("type")
                # Capture the brief from the tool_call event; this fires as
                # the LLM issues the call, before the executor runs. We
                # forward the event unchanged so the trace panel still shows
                # it.
                if etype == "tool_call" and event.get("name") == "propose_prose_continuation":
                    raw_input = event.get("input") or {}
                    if isinstance(raw_input, dict):
                        brief_payload = raw_input
                if isinstance(event.get("round"), int):
                    result.rounds = max(result.rounds, event["round"] + 1)
                yield event
        except Exception as exc:
            logger.exception("ChapterContinuer agent loop failed")
            result.error = f"agent loop 执行失败: {exc}"
            yield {"type": "error", "message": result.error}
            yield {"type": "summary", "runner": self.name, **_summary(result, t0)}
            return

        if brief_payload is None:
            result.error = (
                "LLM 未调用 propose_prose_continuation；降级为返回 brief 未生成"
            )
            yield {"type": "warning", "message": result.error}
            yield {"type": "summary", "runner": self.name, **_summary(result, t0)}
            return

        # Phase 2 — streaming composer.
        writing_brief = brief_payload.get("writing_brief") or {}
        anchor_block_id = brief_payload.get("anchor_block_id") or context.get(
            "last_block_id", ""
        )
        try:
            target_wc = int(brief_payload.get("target_word_count") or 600)
        except (TypeError, ValueError):
            target_wc = 600

        # Resolve a preset prompt. We default to an empty user preset so the
        # composer's built-in system prompt carries; callers who want a
        # specific writing voice can inject preset_id from context.
        preset_prompt = ""
        preset_id = context.get("preset_id") or ""
        if preset_id:
            try:
                from ..preset_service import PresetService

                preset = PresetService().get(preset_id)
                if preset and preset.get("system_prompt"):
                    preset_prompt = preset["system_prompt"]
            except Exception:  # noqa: BLE001
                logger.warning("ChapterContinuer: preset %s lookup failed", preset_id)

        # Merge continuation hint into brief so the composer sees it.
        hint = brief_payload.get("continuation_hint")
        if hint and "continuation_hint" not in writing_brief:
            writing_brief["continuation_hint"] = hint
        writing_brief.setdefault("target_word_count", target_wc)

        from ..writer import WriterComposer

        composer = WriterComposer(llm_router=self.router)
        buffer: list[str] = []
        try:
            async for chunk in composer.compose_stream(writing_brief, preset_prompt):
                if not chunk:
                    continue
                buffer.append(chunk)
                yield {
                    "type": "writer_token",
                    "runner": self.name,
                    "chunk": chunk,
                }
        except Exception as exc:
            logger.exception("WriterComposer stream failed")
            result.error = f"WriterComposer 流失败: {exc}"
            yield {"type": "error", "message": result.error}
            yield {"type": "summary", "runner": self.name, **_summary(result, t0)}
            return

        full_text = "".join(buffer).strip()
        if not full_text:
            result.error = "WriterComposer 未产生任何正文"
            yield {"type": "error", "message": result.error}
            yield {"type": "summary", "runner": self.name, **_summary(result, t0)}
            return

        render = _build_continuation_render(
            anchor_block_id=anchor_block_id,
            chapter_id=chapter_id,
            chapter_label=context.get("chapter_label") or f"第{context.get('chapter_order', '?')}章",
            full_text=full_text,
            target_wc=target_wc,
        )
        result.cards.append(render)

        # Emit as a synthetic tool_result so the existing frontend trace panel
        # picks up the render via the same dispatch as every other runner.
        yield {
            "type": "tool_result",
            "runner": self.name,
            "name": "propose_prose_continuation",
            "summary": f"续写已生成：{len(full_text)} 字",
            "full_result": full_text,
            "render": render,
            "status": "ok",
        }
        result.verdict = f"生成 {len(full_text)} 字"
        yield {"type": "summary", "runner": self.name, **_summary(result, t0)}


def _build_continuation_render(
    *,
    anchor_block_id: str,
    chapter_id: str,
    chapter_label: str,
    full_text: str,
    target_wc: int,
) -> dict[str, Any]:
    """Wrap the generated prose in a ProseDiffRender with source=splice_block.

    This re-uses the existing ProseDiffView card on the frontend — no new
    render type needed (per §B.1 of the plan: "ProseContinuationCard 即
    ProseDiffView 变体"). The single hunk has ``original=""`` so the card
    renders as a pure insert after the anchor block.
    """
    from ....schemas.writer_agent_schemas import ProseDiffRender, ToolRenderAction

    hunk = {
        "hunk_id": f"continuation_{uuid.uuid4().hex[:8]}",
        "original": "",
        "replacement": full_text,
        "reason": "章尾续写",
        "severity": "medium",
        "category": "continuation",
        "location_hint": f"after block={anchor_block_id}",
    }
    data = {
        "scope": "manuscript_block",
        "target_id": anchor_block_id,
        "chapter_label": chapter_label,
        "hunks": [hunk],
        "word_delta": len(full_text),
        "source": "splice_block",
    }
    return ProseDiffRender(
        data=data,
        actions=[
            ToolRenderAction(
                label=f"采纳续写（{len(full_text)} 字）",
                kind="apply_hunks",
                variant="primary",
            ),
        ],
    ).model_dump(mode="json")


def _summary(result: OneClickResult, t0: float) -> dict[str, Any]:
    result.elapsed_ms = int((time.monotonic() - t0) * 1000)
    return {
        "verdict": result.verdict,
        "card_count": len(result.cards),
        "cards": result.cards,
        "rounds": result.rounds,
        "elapsed_ms": result.elapsed_ms,
        "error": result.error,
    }
