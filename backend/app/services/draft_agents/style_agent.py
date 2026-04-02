"""风格分析 Agent — 从原文中提取风格特征，不调用 LLM。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from ...models.project import ProjectManager

logger = logging.getLogger(__name__)

DIALOGUE_PATTERN = re.compile(r'[""「」『』]')
SHORT_SENTENCE_THRESHOLD = 20
LONG_SENTENCE_THRESHOLD = 60


class StyleAgent:
    """从原文中提取风格特征供 WriterAgent 参考。"""

    def analyze(self, project_id: str, chapter_id: str = "") -> Dict[str, Any]:
        """
        分析目标章节（或全文）的风格特征。

        Returns:
            style_hints 字典，包含对话/叙述比例、句式节奏、人称视角等。
        """
        text = self._load_chapter_text(project_id, chapter_id)
        if not text:
            logger.info("StyleAgent: 未找到可分析的章节文本，返回默认风格。")
            return self._default_hints()

        hints = {
            "dialogue_ratio": self._dialogue_ratio(text),
            "avg_sentence_length": self._avg_sentence_length(text),
            "rhythm": self._sentence_rhythm(text),
            "pov_person": self._detect_pov_person(text),
            "sample_length": len(text),
            "rendered_hints": "",
        }
        hints["rendered_hints"] = self._render_hints(hints)
        logger.info(
            "StyleAgent: 风格分析完成 — dialogue=%.0f%%, avg_len=%.0f, pov=%s",
            hints["dialogue_ratio"] * 100,
            hints["avg_sentence_length"],
            hints["pov_person"],
        )
        return hints

    def _load_chapter_text(self, project_id: str, chapter_id: str) -> str:
        """从 chapter_segments.json 中提取目标章节文本。"""
        try:
            segments = ProjectManager.load_project_json(project_id, "chapter_segments.json")
            if not segments:
                return ""
            for chapter in segments.get("chapters", []):
                if chapter_id and chapter.get("chapter_id") != chapter_id:
                    continue
                text = chapter.get("text", "")
                if text:
                    return text[:15000]
            first_chapter = (segments.get("chapters") or [{}])[0] if not chapter_id else {}
            return first_chapter.get("text", "")[:15000]
        except Exception:
            return ""

    def _dialogue_ratio(self, text: str) -> float:
        """计算对话在文本中的占比。"""
        dialogue_chars = 0
        in_dialogue = False
        open_marks = set('"「『"')
        close_marks = set('"」』"')
        for char in text:
            if char in open_marks:
                in_dialogue = True
            elif char in close_marks:
                in_dialogue = False
            elif in_dialogue:
                dialogue_chars += 1
        total = max(len(text), 1)
        return min(dialogue_chars / total, 1.0)

    def _avg_sentence_length(self, text: str) -> float:
        """计算平均句长。"""
        sentences = re.split(r'[。！？!?\n]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 2]
        if not sentences:
            return 30.0
        return sum(len(s) for s in sentences) / len(sentences)

    def _sentence_rhythm(self, text: str) -> str:
        """判断句式节奏：短促 / 均匀 / 绵长。"""
        avg = self._avg_sentence_length(text)
        if avg < SHORT_SENTENCE_THRESHOLD:
            return "短促紧凑"
        if avg > LONG_SENTENCE_THRESHOLD:
            return "绵长舒展"
        return "均匀适中"

    def _detect_pov_person(self, text: str) -> str:
        """检测文本中的人称视角。"""
        sample = text[:5000]
        first_person_count = sample.count("我") + sample.count("我的")
        third_markers = sum(sample.count(m) for m in ("他", "她", "它", "他们", "她们"))
        if first_person_count > third_markers * 2:
            return "第一人称"
        return "第三人称"

    def _default_hints(self) -> Dict[str, Any]:
        """返回默认风格提示。"""
        return {
            "dialogue_ratio": 0.3,
            "avg_sentence_length": 30.0,
            "rhythm": "均匀适中",
            "pov_person": "第三人称",
            "sample_length": 0,
            "rendered_hints": "风格提示：保持对话与叙述的平衡，句式节奏均匀适中，使用第三人称视角。",
        }

    def _render_hints(self, hints: Dict[str, Any]) -> str:
        """渲染为可放入 prompt 的风格指导文本。"""
        ratio = hints["dialogue_ratio"]
        if ratio > 0.5:
            dialogue_hint = "原文对话占比较高，写作时应以对话驱动场景"
        elif ratio > 0.25:
            dialogue_hint = "原文对话与叙述交替均衡"
        else:
            dialogue_hint = "原文以叙述和描写为主，对话穿插其中"

        return (
            f"风格提示：{dialogue_hint}。"
            f"句式节奏为{hints['rhythm']}（平均句长 {hints['avg_sentence_length']:.0f} 字）。"
            f"视角为{hints['pov_person']}。"
            f"请保持与原文一致的叙事风格和节奏感。"
        )
