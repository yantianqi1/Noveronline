"""Core agent loop: LLM thinks -> calls tools -> gets results -> thinks again,
until LLM decides not to call any more tools.

Ported from the claude-code-from-scratch TypeScript agent loop pattern.
"""

import json
import logging
from typing import Any, Dict, Generator, List

logger = logging.getLogger(__name__)


class AgentLoop:
    """
    Core agent loop: LLM thinks -> calls tools -> gets results -> thinks again,
    until LLM decides not to call any more tools.
    """

    MAX_ROUNDS = 15
    MAX_CONTEXT_CHARS = 200_000  # ~100K tokens for Chinese text

    def __init__(self, llm_client, tools: List[Dict], system_prompt: str, project_id: str):
        """
        Args:
            llm_client: LLMClient instance (with chat_with_tools method)
            tools: List of tool definitions in OpenAI format
            system_prompt: System prompt for the orchestrator
            project_id: Current project ID (passed to tool executors)
        """
        self.client = llm_client
        self.tools = tools
        self.system_prompt = system_prompt
        self.project_id = project_id
        self.messages: List[Dict[str, Any]] = []

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
            try:
                response = self.client.chat_with_tools(
                    messages=[{"role": "system", "content": self.system_prompt}] + self.messages,
                    tools=self.tools,
                    temperature=0.3,
                    max_tokens=4096,
                )
            except Exception as exc:
                yield {"type": "error", "message": f"LLM 调用失败: {str(exc)}"}
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
                yield {"type": "brief_ready", "content": response.content or ""}
                return

            # Execute each tool call
            for tc in response.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_input = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_input = {}

                yield {"type": "tool_call", "name": tool_name, "input": tool_input}

                result = execute_tool(tool_name, tool_input, self.project_id)

                # Add tool result to messages
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

                # Yield truncated summary for frontend display
                summary = result[:200] + "..." if len(result) > 200 else result
                yield {"type": "tool_result", "name": tool_name, "summary": summary}

            # Check context size (rough estimate)
            total_chars = sum(
                len(str(m.get("content", ""))) for m in self.messages
            )
            if total_chars > self.MAX_CONTEXT_CHARS:
                logger.warning("Agent loop context overflow at round %d, forcing brief output", round_num)
                yield {"type": "brief_ready", "content": response.content or "已收集的上下文过长，强制结束收集。"}
                return

        # Max rounds reached
        logger.warning("Agent loop reached MAX_ROUNDS=%d", self.MAX_ROUNDS)
        yield {"type": "brief_ready", "content": (response.content if response else "") or "达到最大轮次，强制结束收集。"}
