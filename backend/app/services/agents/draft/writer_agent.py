"""核心创作 Agent — 组装 prompt 并流式调用 LLM 生成小说正文。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Generator, List, Optional

from ...llm_router import LlmRouter
from ...writer_prompt_formatter import WriterPromptFormatter

logger = logging.getLogger(__name__)

NOVEL_DRAFT_WRITER_MODULE = "novel_draft_writer"
WRITER_TEMPERATURE = 0.8
WRITER_MAX_TOKENS = 8192

WRITER_SYSTEM_PROMPT = """你是一名资深小说家。你将基于提供的上下文设定、角色记忆和创作者指令，创作小说正文。

要求：
1. 只输出小说正文本身，不要输出任何元信息、注释、标题编号或大纲。
2. 保持与原文一致的叙事风格、句式节奏和人称视角。
3. 场景描写要有画面感，对话要贴合角色性格和当前处境。
4. 严格遵守"必须延续的事实"中的设定，不要与之矛盾。
5. 注意"风险提示"中标记的问题，在写作中主动规避。
6. 推进剧情时，让角色的选择和行动有因果逻辑，避免突兀转折。
7. 如果提供了修订意见，请在保留上一版核心情节的基础上针对性修改。
"""


class WriterAgent:
    """核心创作 Agent，组装 prompt 并流式调用 LLM 生成正文。"""

    def __init__(
        self,
        llm_router: Optional[LlmRouter] = None,
        formatter: Optional[WriterPromptFormatter] = None,
    ):
        self.llm_router = llm_router or LlmRouter()
        self.formatter = formatter or WriterPromptFormatter()

    def generate_stream(
        self,
        author_instruction: str,
        context_pack: Dict[str, Any],
        memory_bundle: Dict[str, Any],
        style_hints: Dict[str, Any],
        revision_context: Optional[Dict[str, Any]] = None,
    ) -> Generator[str, None, None]:
        """
        流式生成小说正文。

        Args:
            author_instruction: 创作者的自由输入指令
            context_pack: ContextAgent 收集的上下文包
            memory_bundle: MemoryAgent 收集的记忆包
            style_hints: StyleAgent 分析的风格提示
            revision_context: 可选的修订上下文，包含 previous_text 和 revision_instruction

        Yields:
            每个文本片段 (chunk)
        """
        try:
            client = self.llm_router.build_client(NOVEL_DRAFT_WRITER_MODULE)
        except ValueError as exc:
            raise ValueError(f"{NOVEL_DRAFT_WRITER_MODULE} 未绑定可用模型: {exc}") from exc

        system_prompt = self._build_system_prompt(context_pack, memory_bundle, style_hints)
        user_prompt = self._build_user_prompt(author_instruction, revision_context)

        messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        logger.info(
            "WriterAgent: 开始流式生成 — model=%s, system_len=%d, user_len=%d",
            client.model,
            len(system_prompt),
            len(user_prompt),
        )

        think_buffer = ""
        in_think = False

        for chunk in client.chat_stream(
            messages=messages,
            temperature=WRITER_TEMPERATURE,
            max_tokens=WRITER_MAX_TOKENS,
        ):
            # 过滤 <think>...</think> 标签
            if "<think>" in chunk:
                in_think = True
                think_buffer = chunk
                continue
            if in_think:
                think_buffer += chunk
                if "</think>" in think_buffer:
                    in_think = False
                    after_think = re.sub(r'<think>[\s\S]*?</think>', '', think_buffer)
                    think_buffer = ""
                    if after_think.strip():
                        yield after_think
                continue
            yield chunk

    def _build_system_prompt(
        self,
        context_pack: Dict[str, Any],
        memory_bundle: Dict[str, Any],
        style_hints: Dict[str, Any],
    ) -> str:
        """组装 system prompt。"""
        context_block = self.formatter.format(context_pack)
        memory_context = memory_bundle.get("rendered_context", "")
        style_text = style_hints.get("rendered_hints", "")

        sections = [WRITER_SYSTEM_PROMPT.strip()]

        if style_text:
            sections.append(f"\n## 原文风格参考\n{style_text}")

        continuity_block = self._render_continuity(context_pack)
        if continuity_block:
            sections.append(f"\n## 前章连续性\n{continuity_block}")

        history_block = self._render_history_recall(context_pack)
        if history_block:
            sections.append(f"\n## Canon 历史召回\n{history_block}")

        sections.append(f"\n## 创作上下文\n{context_block}")

        if memory_context:
            sections.append(f"\n## 角色记忆\n{memory_context}")

        return "\n".join(sections)

    def _render_continuity(self, context_pack: Dict[str, Any]) -> str:
        """将 continuity_anchor 渲染为 prompt 文本段。"""
        anchor = context_pack.get("continuity_anchor")
        if not anchor:
            return ""

        lines: List[str] = []

        # 上一章末尾原文
        ending = anchor.get("prev_chapter_ending", "")
        if ending:
            lines.append("### 上章末尾原文（请直接继承语气与节奏）")
            lines.append(ending)

        # 前几章摘要
        summaries = anchor.get("chapter_summaries", [])
        if summaries:
            lines.append("\n### 前章摘要")
            for item in summaries:
                idx = item.get("chapter_order", item.get("chapter_index", "?"))
                title = item.get("title", "")
                summary = item.get("summary", "")
                label = f"第{idx}章"
                if title:
                    label += f"《{title}》"
                lines.append(f"- {label}：{summary}")

        # 未解悬念线
        threads = anchor.get("open_threads", [])
        if threads:
            lines.append("\n### 未解悬念线（需在本章推进或呼应）")
            for thread in threads:
                lines.append(f"- {thread}")

        # 时间线注记
        note = anchor.get("timeline_note", "")
        if note:
            lines.append(f"\n### 时间线注记\n{note}")

        return "\n".join(lines) if lines else ""

    def _render_history_recall(self, context_pack: Dict[str, Any]) -> str:
        recall = context_pack.get("history_recall") or {}
        if not any(recall.get(key) for key in ("recent_anchors", "callback_memories", "active_threads", "world_rules")):
            return ""

        lines: List[str] = []
        recent_anchors = recall.get("recent_anchors", [])
        if recent_anchors:
            lines.append("### 最近3章承接摘要")
            for item in recent_anchors:
                label = f"第{item.get('chapter_order', '?')}章"
                if item.get("title"):
                    label += f"《{item.get('title', '')}》"
                lines.append(f"- {label}：{item.get('summary_text', '')}")

        callback_memories = recall.get("callback_memories", [])
        if callback_memories:
            lines.append("\n### 长线回调记忆")
            for item in callback_memories[:12]:
                lines.append(f"- 第{item.get('chapter_order', '?')}章 · {item.get('summary_text', '')}")

        active_threads = recall.get("active_threads", [])
        if active_threads:
            lines.append("\n### 当前仍未回收的 canon 线索")
            for item in active_threads[:8]:
                lines.append(f"- {item.get('summary_text', '')}")

        world_rules = recall.get("world_rules", [])
        if world_rules:
            lines.append("\n### canon 世界规则")
            for rule in world_rules:
                lines.append(f"- {rule}")

        return "\n".join(lines)

    def _build_user_prompt(
        self,
        author_instruction: str,
        revision_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """组装 user prompt。"""
        if revision_context and revision_context.get("previous_text"):
            return (
                f"上一版正文：\n\n{revision_context['previous_text']}\n\n"
                f"修订意见：{revision_context.get('revision_instruction', '请优化')}\n\n"
                f"创作者补充指令：{author_instruction}\n\n"
                "请根据修订意见在上一版基础上重写正文。"
            )
        return f"创作者指令：{author_instruction}\n\n请根据上述上下文和指令，创作小说正文。"

    @property
    def model_name(self) -> str:
        """返回当前绑定的模型名称。"""
        try:
            return self.llm_router.model_name_for_module(NOVEL_DRAFT_WRITER_MODULE)
        except Exception:
            return ""
