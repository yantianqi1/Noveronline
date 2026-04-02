"""
小说章节切分服务
"""

import re
from typing import Any, Dict, List, Sequence

from .sentence_atlas_builder import build_sentence_atlas

CHAPTER_TITLE_PATTERNS = [
    re.compile(r"^\s*第[零一二三四五六七八九十百千万\d]+[章节回卷幕部集篇][^\n]{0,30}$"),
    re.compile(r"^\s*(序章|楔子|终章|尾声|后记|番外)[^\n]{0,30}$"),
    re.compile(r"^\s*(卷[零一二三四五六七八九十百千万\d]+[^\n]{0,30})$"),
]
FALLBACK_SEGMENT_TARGET = 6000
FALLBACK_SEGMENT_MIN = 2500


class NovelChapterSegmenter:
    def segment_documents(self, documents: Sequence[Dict[str, str]]) -> Dict[str, Any]:
        chapters: List[Dict[str, Any]] = []
        order = 1
        for item in documents:
            for chapter in self._segment_document(item["text"], item["source_name"], order):
                chapters.append(chapter)
                order += 1
        chapters, sentence_atlas = build_sentence_atlas(chapters)
        return {
            "chapter_count": len(chapters),
            "chapters": chapters,
            "sentence_atlas": sentence_atlas,
        }

    def _segment_document(self, text: str, source_name: str, start_order: int) -> List[Dict[str, Any]]:
        lines = text.splitlines()
        title_lines = self._title_line_indexes(lines)
        if title_lines:
            return self._chapters_from_titles(lines, title_lines, source_name, start_order)
        return self._fallback_segments(text, source_name, start_order)

    def _title_line_indexes(self, lines: Sequence[str]) -> List[int]:
        indexes = []
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if stripped and any(pattern.match(stripped) for pattern in CHAPTER_TITLE_PATTERNS):
                indexes.append(idx)
        return indexes

    def _chapters_from_titles(
        self,
        lines: Sequence[str],
        title_lines: Sequence[int],
        source_name: str,
        start_order: int,
    ) -> List[Dict[str, Any]]:
        chapters = []
        boundaries = list(title_lines) + [len(lines)]
        for offset, line_idx in enumerate(title_lines):
            next_idx = boundaries[offset + 1]
            title = lines[line_idx].strip()
            content_lines = lines[line_idx + 1:next_idx]
            content = "\n".join(line for line in content_lines if line.strip()).strip()
            if not content:
                continue
            chapters.append(self._chapter_record(
                source_name=source_name,
                order=start_order + len(chapters),
                title=title,
                content=content,
                start_line=line_idx + 1,
                end_line=next_idx,
            ))
        return chapters or self._fallback_segments("\n".join(lines), source_name, start_order)

    def _fallback_segments(self, text: str, source_name: str, start_order: int) -> List[Dict[str, Any]]:
        paragraphs = [item.strip() for item in re.split(r"\n{2,}", text) if item.strip()]
        if not paragraphs:
            return []
        chapters = []
        buffer: List[str] = []
        buffer_size = 0
        start_line = 1
        line_cursor = 1
        for paragraph in paragraphs:
            paragraph_size = len(paragraph)
            if buffer and buffer_size >= FALLBACK_SEGMENT_MIN and buffer_size + paragraph_size > FALLBACK_SEGMENT_TARGET:
                chapters.append(self._chapter_record(
                    source_name=source_name,
                    order=start_order + len(chapters),
                    title=f"叙事段 {len(chapters) + 1}",
                    content="\n\n".join(buffer),
                    start_line=start_line,
                    end_line=line_cursor,
                ))
                buffer = []
                buffer_size = 0
                start_line = line_cursor + 1
            buffer.append(paragraph)
            buffer_size += paragraph_size
            line_cursor += paragraph.count("\n") + 2
        if buffer:
            chapters.append(self._chapter_record(
                source_name=source_name,
                order=start_order + len(chapters),
                title=f"叙事段 {len(chapters) + 1}",
                content="\n\n".join(buffer),
                start_line=start_line,
                end_line=line_cursor,
            ))
        return chapters

    def _chapter_record(
        self,
        source_name: str,
        order: int,
        title: str,
        content: str,
        start_line: int,
        end_line: int,
    ) -> Dict[str, Any]:
        return {
            "chapter_id": f"chapter_{order:04d}",
            "order": order,
            "title": title,
            "source_name": source_name,
            "content": content,
            "word_count": len(content),
            "source_range": {"start_line": start_line, "end_line": end_line},
        }
