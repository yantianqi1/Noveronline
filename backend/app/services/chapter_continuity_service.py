"""
章节连续性摘要服务
"""

import re
from typing import Any, Dict, List, Optional, Sequence

from .novel_seed_analyzer import NovelSeedAnalyzer


CONFLICT_HINTS = ("冲突", "追杀", "威胁", "对峙", "逼近", "怀疑", "争执", "真相", "抉择", "危机")
SUMMARY_SENTENCE_LIMIT = 2


class ChapterContinuityService:
    def __init__(self, analyzer: Optional[NovelSeedAnalyzer] = None):
        self.analyzer = analyzer or NovelSeedAnalyzer()

    def build(self, chapters: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        return self.build_from_block_analyses(chapters, [], [])

    def build_from_block_analyses(
        self,
        chapters: Sequence[Dict[str, Any]],
        analysis_blocks: Sequence[Dict[str, Any]],
        block_analyses: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        continuity_chapters = []
        block_context = self._block_context_map(analysis_blocks, block_analyses)
        previous_tail = ""
        for item in chapters:
            chapter = self._chapter_summary(item, previous_tail, block_context.get(item["chapter_id"], ""))
            continuity_chapters.append(chapter)
            previous_tail = "；".join(chapter["tail_hooks"][:2]) or chapter["continuity_summary"]
        return {
            "chapter_count": len(continuity_chapters),
            "global_summary": self._global_summary(continuity_chapters),
            "chapters": continuity_chapters,
        }

    def _chapter_summary(
        self,
        chapter: Dict[str, Any],
        previous_tail: str,
        block_plot_summary: str,
    ) -> Dict[str, Any]:
        sentences = self._sentences(chapter["content"])
        analysis = self.analyzer.analyze_text(chapter["content"])
        head_context = previous_tail or block_plot_summary or self._join_sentences(sentences[:SUMMARY_SENTENCE_LIMIT], "剧情起点")
        core_conflicts = self._conflict_sentences(sentences)
        tail_hooks = self._join_sentences(sentences[-SUMMARY_SENTENCE_LIMIT:], "暂无尾部钩子", as_list=True)
        key_characters = [item["name"] for item in analysis["characters"][:6]]
        key_organizations = [item["name"] for item in analysis["organizations"][:4]]
        continuity_summary = (
            f"承接上文：{head_context}。"
            f"本章主要推进：{'；'.join(core_conflicts)}。"
            f"块内主线：{block_plot_summary or '当前章节独立推进'}。"
            f"尾部留下：{'；'.join(tail_hooks)}。"
        )
        return {
            "chapter_id": chapter["chapter_id"],
            "order": chapter["order"],
            "title": chapter["title"],
            "head_context": head_context,
            "core_conflicts": core_conflicts,
            "key_characters": key_characters,
            "key_organizations": key_organizations,
            "tail_hooks": tail_hooks,
            "continuity_summary": continuity_summary,
        }

    def _sentences(self, text: str) -> List[str]:
        parts = re.split(r"[。！？!?]\s*|\n+", text)
        return [item.strip(" \t，,；;") for item in parts if item.strip()]

    def _conflict_sentences(self, sentences: Sequence[str]) -> List[str]:
        selected = [item[:120] for item in sentences if any(hint in item for hint in CONFLICT_HINTS)]
        if selected:
            return selected[:SUMMARY_SENTENCE_LIMIT]
        return self._join_sentences(sentences[:SUMMARY_SENTENCE_LIMIT], "暂无显著冲突", as_list=True)

    def _join_sentences(
        self,
        sentences: Sequence[str],
        default_text: str,
        as_list: bool = False,
    ):
        items = [item[:120] for item in sentences if item]
        if not items:
            return [] if as_list else default_text
        return items if as_list else "；".join(items[:SUMMARY_SENTENCE_LIMIT])

    def _global_summary(self, chapters: Sequence[Dict[str, Any]]) -> str:
        if not chapters:
            return "暂无章节连续性摘要。"
        opening = chapters[0]["continuity_summary"]
        ending = chapters[-1]["continuity_summary"]
        return f"开篇主轴：{opening} 末尾状态：{ending}"

    def _block_context_map(
        self,
        analysis_blocks: Sequence[Dict[str, Any]],
        block_analyses: Sequence[Dict[str, Any]],
    ) -> Dict[str, str]:
        analysis_map = {item.get("block_id", ""): item for item in block_analyses}
        chapter_map = {}
        for block in analysis_blocks:
            block_id = block.get("block_id", "")
            plot_summary = analysis_map.get(block_id, {}).get("plot_summary", "")
            for chapter_id in block.get("owned_chapter_ids", []):
                chapter_map[chapter_id] = plot_summary
        return chapter_map
