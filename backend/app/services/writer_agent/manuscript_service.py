"""Manuscript management service — commit, metadata extraction, export."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

from .novel_db import NovelDB

logger = logging.getLogger(__name__)


class ManuscriptService:
    """High-level manuscript operations wrapping NovelDB."""

    def __init__(self) -> None:
        self._db = NovelDB()

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------

    def commit(
        self,
        project_id: str,
        content: str,
        source_scene_id: str | None = None,
        insert_after_block_id: str | None = None,
        chapter_id: str | None = None,
        chapter_tag: str | None = None,
        pov_entity_id: str | None = None,
        location: str | None = None,
        involved_entities_json: str | None = None,
    ) -> dict[str, Any]:
        """Commit content to the manuscript. Spawns async metadata extraction."""
        block = self._db.commit_manuscript_block(
            project_id, content, source_scene_id, insert_after_block_id,
            chapter_id=chapter_id,
            pov_entity_id=pov_entity_id,
            location=location,
            involved_entities_json=involved_entities_json,
        )
        # Legacy: apply chapter_tag if provided without chapter_id
        if chapter_tag and not chapter_id:
            self._db.tag_manuscript_blocks(project_id, [block["block_id"]], chapter_tag)
            block["chapter_tag"] = chapter_tag

        # Async LLM metadata extraction (best-effort)
        threading.Thread(
            target=self._extract_metadata_safe,
            args=(project_id, block["block_id"], content),
            daemon=True,
        ).start()

        return block

    # ------------------------------------------------------------------
    # CRUD pass-through
    # ------------------------------------------------------------------

    def list_blocks(
        self, project_id: str, include_content: bool = True,
        chapter_id: str | None = None,
    ) -> dict[str, Any]:
        blocks = self._db.list_manuscript_blocks(
            project_id, include_content, chapter_id=chapter_id,
        )
        stats = self._db.get_manuscript_stats(project_id)
        return {
            "blocks": blocks,
            "total_words": stats["total_words"],
            "total_blocks": stats["total_blocks"],
            "chapters": stats.get("chapters", []),
        }

    def get_block(self, project_id: str, block_id: str) -> dict[str, Any] | None:
        return self._db.get_manuscript_block(project_id, block_id)

    def update_block(self, project_id: str, block_id: str, **kwargs: Any) -> dict[str, Any]:
        self._db.update_manuscript_block(project_id, block_id, **kwargs)
        return self._db.get_manuscript_block(project_id, block_id) or {}

    def delete_block(self, project_id: str, block_id: str) -> None:
        self._db.delete_manuscript_block(project_id, block_id)

    def reorder(self, project_id: str, block_ids: list[str]) -> None:
        self._db.reorder_manuscript_blocks(project_id, block_ids)

    def tag_blocks(self, project_id: str, block_ids: list[str], chapter_tag: str) -> int:
        return self._db.tag_manuscript_blocks(project_id, block_ids, chapter_tag)

    def move_block(
        self, project_id: str, block_id: str,
        target_chapter_id: str | None,
    ) -> dict[str, Any]:
        """Move a manuscript block to a different chapter (or unassign)."""
        self._db.move_manuscript_block_to_chapter(
            project_id, block_id, target_chapter_id,
        )
        return self._db.get_manuscript_block(project_id, block_id) or {}

    def get_stats(self, project_id: str) -> dict[str, Any]:
        return self._db.get_manuscript_stats(project_id)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_text(self, project_id: str, fmt: str = "txt") -> str:
        text = self._db.export_manuscript(project_id)
        if fmt == "md":
            # Insert chapter headings where chapter changes
            blocks = self._db.list_manuscript_blocks(project_id, include_content=True)
            # Build chapter_id -> title lookup
            stats = self._db.get_manuscript_stats(project_id)
            ch_titles = {
                ch["chapter_id"]: f"第{ch['chapter_order']}章 · {ch['title']}"
                for ch in stats.get("chapters", [])
            }
            parts: list[str] = []
            current_chapter = None
            for b in blocks:
                cid = b.get("chapter_id")
                heading = ch_titles.get(cid) or b.get("chapter_tag")
                if heading and heading != current_chapter:
                    parts.append(f"\n# {heading}\n")
                    current_chapter = heading
                parts.append(b["content"])
            return "\n\n".join(parts)
        return text

    # ------------------------------------------------------------------
    # Async metadata extraction
    # ------------------------------------------------------------------

    def _extract_metadata_safe(
        self, project_id: str, block_id: str, content: str,
    ) -> None:
        """Best-effort metadata extraction — never raises."""
        try:
            self._extract_metadata(project_id, block_id, content)
        except Exception:
            logger.warning(
                "Manuscript metadata extraction failed for block %s",
                block_id, exc_info=True,
            )

    def _extract_metadata(
        self, project_id: str, block_id: str, content: str,
    ) -> None:
        from ..llm_router import LlmRouter

        router = LlmRouter()
        client = router.build_client("writer_orchestrator")

        # Get previous block summary for context
        blocks = self._db.list_manuscript_blocks(project_id, include_content=False)
        current_idx = None
        for i, b in enumerate(blocks):
            if b["block_id"] == block_id:
                current_idx = i
                break
        prev_summary = ""
        if current_idx and current_idx > 0:
            prev_summary = blocks[current_idx - 1].get("summary") or ""

        prompt = (
            "请分析以下小说段落，提取结构化信息。\n\n"
        )
        if prev_summary:
            prompt += f"前一段摘要：{prev_summary}\n\n"
        prompt += f"当前段落：\n{content}\n\n"
        prompt += (
            "请以 JSON 格式返回：\n"
            "{\n"
            '  "summary": "1-2句概括本段发生了什么",\n'
            '  "open_threads": ["未解决的伏笔/悬念1", "..."],\n'
            '  "pov_entity": "视角人物名称",\n'
            '  "involved_entities": ["出场角色名称1", "..."],\n'
            '  "location": "场景地点",\n'
            '  "narrative_note": "叙事状态（基调、节奏、张力）"\n'
            "}\n"
            "只返回 JSON，不要其他内容。"
        )

        messages = [{"role": "user", "content": prompt}]
        result = client.chat_json(messages, temperature=0.2, max_tokens=2048)
        if not isinstance(result, dict):
            logger.warning("Metadata extraction returned non-dict: %s", type(result))
            return

        # Resolve entity names to IDs
        pov_name = result.get("pov_entity", "")
        pov_entity_id = self._resolve_entity_name(project_id, pov_name)

        involved_names = result.get("involved_entities", [])
        involved_ids = []
        for name in involved_names:
            eid = self._resolve_entity_name(project_id, name)
            involved_ids.append(eid or name)

        self._db.update_manuscript_block(
            project_id, block_id,
            summary=result.get("summary", ""),
            open_threads_json=json.dumps(
                result.get("open_threads", []), ensure_ascii=False
            ),
            pov_entity_id=pov_entity_id or pov_name,
            involved_entities_json=json.dumps(involved_ids, ensure_ascii=False),
            location=result.get("location", ""),
            narrative_note=result.get("narrative_note", ""),
        )
        logger.info("Metadata extracted for manuscript block %s", block_id)

    def _resolve_entity_name(self, project_id: str, name: str) -> str | None:
        if not name:
            return None
        entity = self._db.get_entity(project_id, name)
        if entity:
            return entity["entity_id"]
        return None
