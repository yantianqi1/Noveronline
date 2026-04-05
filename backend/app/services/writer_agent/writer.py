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
            pov_lines = [f"{pov.get('name', '未知')}：{pov.get('profile_summary', '')}"]
            if pov.get("core_drive"):
                pov_lines.append(f"核心驱动：{pov['core_drive']}")
            if pov.get("surface_mask"):
                pov_lines.append(f"表面表现：{pov['surface_mask']}")
            if pov.get("hidden_tension"):
                pov_lines.append(f"内在矛盾：{pov['hidden_tension']}")
            if pov.get("speech_style"):
                pov_lines.append(f"说话风格：{pov['speech_style']}")
            if pov.get("key_details"):
                pov_lines.append(f"关键设定：{pov['key_details']}")
            sections.append(f"\n### 视角角色\n" + "\n".join(pov_lines))

        if brief.get("involved_characters"):
            char_blocks = []
            for c in brief["involved_characters"]:
                c_lines = [f"**{c.get('name', '?')}**：{c.get('profile_summary', c.get('key_traits', ''))}"]
                if c.get("core_drive"):
                    c_lines.append(f"  核心驱动：{c['core_drive']}")
                if c.get("hidden_tension"):
                    c_lines.append(f"  内在矛盾：{c['hidden_tension']}")
                if c.get("key_details"):
                    c_lines.append(f"  关键设定：{c['key_details']}")
                char_blocks.append("\n".join(c_lines))
            sections.append(f"\n### 涉及角色\n" + "\n".join(char_blocks))

        if brief.get("relationships"):
            rels = "\n".join(
                f"- {r.get('between', '?')}：{r.get('summary', '')}"
                for r in brief["relationships"]
            )
            sections.append(f"\n### 角色关系\n{rels}")

        if brief.get("setting_details"):
            sections.append(f"\n### 相关设定\n{brief['setting_details']}")

        if brief.get("chapter_outline"):
            outline_lines = []
            for beat in brief["chapter_outline"]:
                order = beat.get("scene_order", "?")
                title = beat.get("title", "")
                summary = beat.get("summary", "")
                outline_lines.append(f"{order}. {title}：{summary}")
            sections.append(f"\n### 本章大纲\n" + "\n".join(outline_lines))

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

        # For continue, include continuation context and tail text
        if brief.get("continuation_context"):
            cc = brief["continuation_context"]
            if cc.get("narrative_note"):
                sections.append(f"\n### 叙事状态\n{cc['narrative_note']}")
            if cc.get("last_location"):
                sections.append(f"\n### 当前地点\n{cc['last_location']}")
            if cc.get("tail_text"):
                sections.append(
                    f"\n### 续写起点（从此处继续，保持文风和节奏一致）\n{cc['tail_text']}"
                )
        elif brief.get("continue_from"):
            sections.append(f"\n### 续写起点（从此处继续）\n{brief['continue_from']}")

        # Fallback: if brief parsing failed, the raw orchestrator output
        # still contains all the collected information
        if brief.get("raw_context"):
            sections.append(f"\n### 编排层收集的完整上下文\n{brief['raw_context']}")

        # Inject raw tool results — the most reliable source of context
        if brief.get("_tool_results"):
            tool_sections = []
            for tr in brief["_tool_results"]:
                tool_name = tr.get("tool", "")
                result = tr.get("result", "")
                # Skip empty/not-found results
                if not result or "未找到" in result or "暂无" in result or "没有找到" in result:
                    continue
                # Clean up structural formatting to reduce "report-like" influence
                cleaned = self._clean_tool_result(tool_name, result)
                if cleaned:
                    tool_sections.append(cleaned)
            if tool_sections:
                sections.append("\n### 参考资料\n" + "\n\n---\n\n".join(tool_sections))

        return "\n".join(sections)

    @staticmethod
    def _clean_tool_result(tool_name: str, result: str) -> str:
        """Clean tool output into prose-friendly reference text."""
        # Map tool names to readable labels
        labels = {
            "query_entity": "角色设定",
            "query_relationship": "角色关系",
            "query_chapter": "章节信息",
            "query_scene": "场景内容",
            "search_settings": "相关设定",
            "get_recent_scenes": "前序场景",
            "get_world_state": "世界状态",
            "get_open_threads": "伏笔线索",
            "get_manuscript_context": "稿件上下文",
            "search_manuscript": "稿件搜索",
            "get_manuscript_stats": "稿件概况",
        }
        label = labels.get(tool_name, tool_name)

        # Remove structural prefixes that could influence prose style
        import re
        cleaned = result
        # Remove 【Type】 markers
        cleaned = re.sub(r"【\w+】", "", cleaned)
        # Remove "重要性：xxx" metadata lines
        cleaned = re.sub(r"重要性：\S+\s*", "", cleaned)
        # Remove "状态：xxx" metadata
        cleaned = re.sub(r"状态：\S+\s*", "", cleaned)
        # Remove "字数：\d+" metadata
        cleaned = re.sub(r"字数：\d+\s*", "", cleaned)

        return f"[{label}]\n{cleaned.strip()}"

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

        else:
            parts.append(brief.get("user_instruction", "请开始创作。"))

        return "\n".join(parts)

    @property
    def model_name(self) -> str:
        return self.router.model_name_for_module("writer_composer")
