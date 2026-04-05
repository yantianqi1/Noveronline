"""Core agent loop: LLM thinks -> calls tools -> gets results -> thinks again,
until LLM decides not to call any more tools.

Ported from the claude-code-from-scratch TypeScript agent loop pattern.
"""

import concurrent.futures
import json
import logging
import time
from typing import Any, Dict, Generator, List

from .tools import TOOL_DISPLAY_FORMATTERS

logger = logging.getLogger(__name__)


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

    def run(self, user_message: str) -> Generator[Dict[str, Any], None, None]:
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
                response = self.client.chat_with_tools(
                    messages=full_messages,
                    tools=self.tools,
                    temperature=0.3,
                    max_tokens=8192,
                )
            except Exception as exc:
                yield {"type": "error", **self._stamp(), "message": f"LLM 调用失败: {str(exc)}"}
                return

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
                yield {"type": "thinking", **self._stamp(), "content": response.content.strip()}

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
                yield {"type": "tool_call", **self._stamp(), "name": tool_name, "input": tool_input, "display": display}
                pending.append((tc, tool_name, tool_input))

            # Execute all tools in parallel (all are read-only SQLite queries)
            def _run_tool(item):
                tc, tool_name, tool_input = item
                result = execute_tool(tool_name, tool_input, self.project_id)
                return tc, tool_name, result

            results_map: Dict[str, tuple] = {}
            if len(pending) == 1:
                # Skip thread pool overhead for single tool call
                tc, tool_name, result = _run_tool(pending[0])
                results_map[tc.id] = (tc, tool_name, result)
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
                    futures = {pool.submit(_run_tool, item): item[0].id for item in pending}
                    for future in concurrent.futures.as_completed(futures):
                        tc, tool_name, result = future.result()
                        results_map[tc.id] = (tc, tool_name, result)

            # Append results in original order (deterministic message history)
            for tc, tool_name, tool_input in pending:
                _, resolved_name, result = results_map[tc.id]
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
                summary = result[:200] + "..." if len(result) > 200 else result
                yield {"type": "tool_result", **self._stamp(), "name": resolved_name, "summary": summary, "full_result": result}

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
