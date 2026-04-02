"""Writer composition layer — streams prose from the strongest LLM model."""

import re
import logging
from typing import Generator

logger = logging.getLogger(__name__)

WRITER_TEMPERATURE = 0.8
WRITER_MAX_TOKENS = 8192
THINK_TAG_RE = re.compile(r"<think>[\s\S]*?</think>", re.DOTALL)


class WriterComposer:
    """Receives a writing_brief + preset prompt, streams high-quality prose."""

    def __init__(self, llm_router=None):
        from ...services.llm_router import LlmRouter
        self.router = llm_router or LlmRouter()

    def compose_stream(
        self, writing_brief: dict, preset_prompt: str
    ) -> Generator[str, None, None]:
        """
        Stream prose text from the writer model.

        Args:
            writing_brief: Structured writing instructions from the orchestrator
            preset_prompt: User's writing style system prompt (from writer_presets)
        """
        client = self.router.build_client("writer_composer")

        system_prompt = self._build_system_prompt(preset_prompt, writing_brief)
        user_prompt = self._build_user_prompt(writing_brief)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        think_buffer = ""
        in_think = False

        for chunk in client.chat_stream(
            messages, temperature=WRITER_TEMPERATURE, max_tokens=WRITER_MAX_TOKENS
        ):
            # Filter <think>...</think> tags (some models produce these)
            if "<think>" in chunk:
                in_think = True
                think_buffer = chunk
                continue
            if in_think:
                think_buffer += chunk
                if "</think>" in think_buffer:
                    in_think = False
                    after_think = re.sub(r"<think>[\s\S]*?</think>", "", think_buffer)
                    think_buffer = ""
                    if after_think.strip():
                        yield after_think
                continue
            yield chunk

    def _build_system_prompt(self, preset_prompt: str, brief: dict) -> str:
        """Combine user preset with structured brief context."""
        sections = [preset_prompt.strip()]

        # Add brief context sections
        if brief.get("pov"):
            pov = brief["pov"]
            sections.append(f"\n### 视角角色\n{pov.get('name', '未知')}：{pov.get('profile_summary', '')}")

        if brief.get("involved_characters"):
            chars = "\n".join(
                f"- {c.get('name', '?')}：{c.get('key_traits', '')}"
                for c in brief["involved_characters"]
            )
            sections.append(f"\n### 涉及角色\n{chars}")

        if brief.get("relationships"):
            rels = "\n".join(
                f"- {r.get('between', '?')}：{r.get('summary', '')}"
                for r in brief["relationships"]
            )
            sections.append(f"\n### 角色关系\n{rels}")

        if brief.get("scene_context"):
            sections.append(f"\n### 场景上下文\n{brief['scene_context']}")

        if brief.get("recent_narrative"):
            sections.append(f"\n### 前文衔接\n{brief['recent_narrative']}")

        if brief.get("open_threads"):
            threads = "\n".join(f"- {t}" for t in brief["open_threads"])
            sections.append(f"\n### 未解决悬念\n{threads}")

        if brief.get("constraints"):
            constraints = "\n".join(f"- {c}" for c in brief["constraints"])
            sections.append(f"\n### 约束（不能违反）\n{constraints}")

        # For rewrite/expand, include original text
        if brief.get("original_text"):
            sections.append(f"\n### 原文\n{brief['original_text']}")

        # For continue, include the continuation point
        if brief.get("continue_from"):
            sections.append(f"\n### 续写起点（从此处继续）\n{brief['continue_from']}")

        return "\n".join(sections)

    def _build_user_prompt(self, brief: dict) -> str:
        """Build user message from brief."""
        task = brief.get("task", "write_scene")
        parts = []

        if task == "write_scene":
            if brief.get("scene_focus"):
                parts.append(f"场景：{brief['scene_focus']}")
            if brief.get("user_instruction"):
                parts.append(f"创作指令：{brief['user_instruction']}")
            if not parts:
                parts.append("请根据以上设定和上下文，创作本场景的正文。")

        elif task == "continue":
            parts.append("请从上述续写起点继续写作。")
            if brief.get("user_instruction"):
                parts.append(f"指令：{brief['user_instruction']}")

        elif task == "rewrite":
            parts.append("请按以下指令改写上述原文。")
            if brief.get("rewrite_instruction"):
                parts.append(brief["rewrite_instruction"])
            elif brief.get("user_instruction"):
                parts.append(brief["user_instruction"])

        elif task == "expand":
            parts.append("请扩写上述原文，展开更多细节。")
            if brief.get("expand_instruction"):
                parts.append(brief["expand_instruction"])
            elif brief.get("user_instruction"):
                parts.append(brief["user_instruction"])

        elif task == "outline":
            parts.append("请为本章生成场景拆分大纲，以 JSON 数组格式输出。")
            if brief.get("user_instruction"):
                parts.append(f"指令：{brief['user_instruction']}")

        elif task == "consistency_check":
            parts.append("请逐条检查场景正文与设定的一致性，输出矛盾报告（JSON 格式）。")

        else:
            parts.append(brief.get("user_instruction", "请开始创作。"))

        return "\n".join(parts)

    @property
    def model_name(self) -> str:
        return self.router.model_name_for_module("writer_composer")
