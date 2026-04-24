"""Core agent loop: LLM thinks -> calls tools -> gets results -> thinks again,
until LLM decides not to call any more tools.

Ported from the claude-code-from-scratch TypeScript agent loop pattern.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any, Dict, List

from .tools import TOOL_DISPLAY_FORMATTERS

logger = logging.getLogger(__name__)

# Write tools modify DB state -- must execute serially to avoid SQLite WAL contention.
# Write tools modify DB state -- must execute serially to avoid SQLite WAL contention.
_WRITE_TOOL_NAMES = {
    "manage_entity",
    "manage_thread",
    "manage_world_rule",
    "manage_relationship",
    "record_character_event",
    "splice_block",
    "rewrite_span",
    "upsert_forbidden_lexicon",
}

# propose_* tools draft structured cards for the user to adopt. They read
# DB + assemble a render payload but do NOT write — so they can be run in
# the read-parallel phase alongside other read tools without SQLite WAL
# contention.
_PROPOSE_TOOL_NAMES = {
    "propose_outline_scene",
    "propose_chapter_structure",
    "propose_prose_continuation",
    "propose_splice_block",
    "propose_rewrite_span",
    "propose_relationship",
}

# Read tools that never mutate state.
_READ_TOOL_NAMES_EXCLUDED = _WRITE_TOOL_NAMES


class AgentLoop:
    """
    Core agent loop: LLM thinks -> calls tools -> gets results -> thinks again,
    until LLM decides not to call any more tools.
    """

    MAX_ROUNDS = 15
    MAX_CONTEXT_CHARS = 200_000  # ~100K tokens for Chinese text
    COMPRESS_THRESHOLD = int(MAX_CONTEXT_CHARS * 0.70)  # 140K — compress old tool results
    CRITICAL_THRESHOLD = int(MAX_CONTEXT_CHARS * 0.90)  # 180K — force stop

    def __init__(self, llm_client, tools: List[Dict], system_prompt: str, project_id: str, t0: float = 0.0):
        """
        Args:
            llm_client: LLMClient instance (with chat_with_tools method)
            tools: List of tool definitions in OpenAI format
            system_prompt: System prompt for the orchestrator
            project_id: Current project ID (passed to tool executors)
            t0: monotonic start time from orchestrator (for elapsed_ms)
        """
        self.client = llm_client
        self.tools = tools
        self.system_prompt = system_prompt
        self.project_id = project_id
        self.t0 = t0 or time.monotonic()
        self.messages: List[Dict[str, Any]] = []
        self.total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _stamp(self) -> Dict[str, Any]:
        return {
            "ts": time.strftime("%H:%M:%S"),
            "elapsed_ms": int((time.monotonic() - self.t0) * 1000),
        }

    def _compress_old_tool_results(self) -> None:
        """Replace tool results older than the last 4 with truncated summaries."""
        tool_msg_indices = [
            i for i, m in enumerate(self.messages) if m.get("role") == "tool"
        ]
        if len(tool_msg_indices) <= 4:
            return
        for idx in tool_msg_indices[:-4]:
            content = self.messages[idx]["content"]
            if len(content) > 300:
                self.messages[idx]["content"] = (
                    content[:200] + f"\n... [已压缩，原文 {len(content)} 字]"
                )

    def _context_chars(self) -> int:
        return sum(len(str(m.get("content", ""))) for m in self.messages)

    async def run(self, user_message: str) -> AsyncIterator[Dict[str, Any]]:
        """
        Run the agent loop. Yields events:
        - {"type": "tool_call", "name": str, "input": dict}
        - {"type": "tool_result", "name": str, "summary": str}
        - {"type": "brief_ready", "content": str}
        - {"type": "error", "message": str}
        """
        from .tool_executors import execute_tool

        self.messages.append({"role": "user", "content": user_message})

        response = None

        for round_num in range(self.MAX_ROUNDS):
            full_messages = [{"role": "system", "content": self.system_prompt}] + self.messages
            yield {
                "type": "prompt_snapshot",
                **self._stamp(),
                "phase": "orchestrator",
                "round": round_num,
                "messages": full_messages,
            }
            try:
                response = await self.client.chat_with_tools(
                    messages=full_messages,
                    tools=self.tools,
                    temperature=0.3,
                    max_tokens=8192,
                )
            except Exception as exc:
                yield {"type": "error", **self._stamp(), "message": f"LLM 调用失败: {str(exc)}"}
                return

            # Accumulate token usage
            usage = getattr(response, "_usage", None)
            if usage:
                for k in self.total_usage:
                    self.total_usage[k] += usage.get(k, 0)

            # Build assistant message for history
            assistant_msg: Dict[str, Any] = {"role": "assistant", "content": response.content or ""}
            if response.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in response.tool_calls
                ]
            self.messages.append(assistant_msg)

            # No tool calls = LLM is done, output is the brief
            if not response.tool_calls:
                yield {"type": "brief_ready", **self._stamp(), "content": response.content or ""}
                return

            # Yield LLM thinking text if present alongside tool calls
            if response.content and response.content.strip():
                yield {"type": "thinking", **self._stamp(), "round": round_num, "content": response.content.strip()}

            # --- Parallel tool execution ---
            # Yield all tool_call events first (frontend shows them immediately)
            pending = []
            for tc in response.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                display_fn = TOOL_DISPLAY_FORMATTERS.get(tool_name)
                display = display_fn(tool_input) if display_fn else tool_name
                yield {"type": "tool_call", **self._stamp(), "round": round_num, "name": tool_name, "input": tool_input, "display": display}
                pending.append((tc, tool_name, tool_input))

            # Execute tools: read-only tools run in parallel via asyncio, write tools run serially.
            def _run_tool_sync(item):
                tc_inner, tool_name_inner, tool_input_inner = item
                t_start = time.monotonic()
                try:
                    ret = execute_tool(tool_name_inner, tool_input_inner, self.project_id)
                    # ``execute_tool`` always returns a dict with {result, render?}.
                    result_text = ret.get("result", "") if isinstance(ret, dict) else str(ret)
                    render_payload = ret.get("render") if isinstance(ret, dict) else None
                    elapsed = int((time.monotonic() - t_start) * 1000)
                    return tc_inner, tool_name_inner, result_text, render_payload, "ok", elapsed
                except Exception as exc:
                    logger.exception("Tool %s failed", tool_name_inner)
                    elapsed = int((time.monotonic() - t_start) * 1000)
                    return tc_inner, tool_name_inner, f"工具执行失败: {exc}", None, "error", elapsed

            read_pending = [p for p in pending if p[1] not in _WRITE_TOOL_NAMES]
            write_pending = [p for p in pending if p[1] in _WRITE_TOOL_NAMES]

            results_map: Dict[str, tuple] = {}

            # Phase A: read tools + propose tools in parallel via asyncio.to_thread.
            # propose_* tools read DB and build render payloads but never mutate,
            # so they share the read lane without WAL contention.
            if read_pending:
                read_coros = [
                    asyncio.to_thread(_run_tool_sync, item) for item in read_pending
                ]
                read_results = await asyncio.gather(*read_coros)
                for entry in read_results:
                    tc_r = entry[0]
                    results_map[tc_r.id] = entry

            # Phase B: write tools serially (SQLite WAL safety)
            for item in write_pending:
                entry = await asyncio.to_thread(_run_tool_sync, item)
                tc_w = entry[0]
                results_map[tc_w.id] = entry

            # Append results in original order (deterministic message history)
            for tc, tool_name, tool_input in pending:
                _, resolved_name, result, render, status, tool_ms = results_map[tc.id]
                # LLM-visible message carries text only — render JSON would
                # pollute token budget without helping the model.
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                summary = result[:200] + "..." if len(result) > 200 else result
                yield {
                    "type": "tool_result",
                    **self._stamp(),
                    "round": round_num,
                    "name": resolved_name,
                    "summary": summary,
                    "full_result": result,
                    "render": render,
                    "status": status,
                    "tool_elapsed_ms": tool_ms,
                }

            # --- Progressive context compression ---
            total_chars = self._context_chars()
            if total_chars > self.COMPRESS_THRESHOLD:
                self._compress_old_tool_results()
                total_chars = self._context_chars()
            if total_chars > self.CRITICAL_THRESHOLD:
                logger.warning("Agent loop context overflow at round %d after compression, forcing brief output", round_num)
                yield {"type": "brief_ready", **self._stamp(), "content": response.content or "已收集的上下文过长，强制结束收集。"}
                return

        # Max rounds reached
        logger.warning("Agent loop reached MAX_ROUNDS=%d", self.MAX_ROUNDS)
        yield {"type": "brief_ready", **self._stamp(), "content": (response.content if response else "") or "达到最大轮次，强制结束收集。"}
