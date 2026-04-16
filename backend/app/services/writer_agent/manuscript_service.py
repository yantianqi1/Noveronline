"""Manuscript management service -- commit, metadata extraction, export."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from ...database import get_engine
from ...repositories import EntityRepository, ManuscriptRepository
from ..assets.manuscript_adapter import ManuscriptAssetAdapter

logger = logging.getLogger(__name__)


def _get_adapter(project_id: str) -> ManuscriptAssetAdapter:
    """Build a ManuscriptAssetAdapter for the given project.

    The adapter owns the complex commit/stats/FTS logic that lives on top
    of the raw assets table.  A chapter_lookup callback is wired via the
    ChapterRepository so chapter tags resolve correctly.
    """
    from ...repositories import ChapterRepository

    engine = get_engine()
    chapter_repo = ChapterRepository(engine)

    def chapter_lookup(chapter_id: str | None) -> dict | None:
        if not chapter_id:
            return None
        return chapter_repo.get_chapter(project_id, chapter_id)

    return ManuscriptAssetAdapter(project_id, chapter_lookup=chapter_lookup)


class ManuscriptService:
    """High-level manuscript operations wrapping repository layer."""

    def __init__(self) -> None:
        self._engine = get_engine()

    def _adapter(self, project_id: str) -> ManuscriptAssetAdapter:
        return _get_adapter(project_id)

    def _entity_repo(self) -> EntityRepository:
        return EntityRepository(self._engine)

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------

    async def commit(
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
        adapter = self._adapter(project_id)
        block = adapter.commit(
            content,
            source_scene_id=source_scene_id,
            insert_after_block_id=insert_after_block_id,
            chapter_id=chapter_id,
            pov_entity_id=pov_entity_id,
            location=location,
            involved_entities_json=involved_entities_json,
        )
        # Legacy: apply chapter_tag if provided without chapter_id
        if chapter_tag and not chapter_id:
            adapter.tag_blocks([block["block_id"]], chapter_tag)
            block["chapter_tag"] = chapter_tag

        # Async LLM metadata extraction (best-effort, fire-and-forget)
        asyncio.create_task(
            self._extract_metadata_async(project_id, block["block_id"], content)
        )

        return block

    # ------------------------------------------------------------------
    # CRUD pass-through
    # ------------------------------------------------------------------

    def list_blocks(
        self, project_id: str, include_content: bool = True,
        chapter_id: str | None = None,
    ) -> dict[str, Any]:
        adapter = self._adapter(project_id)
        blocks = adapter.list_blocks(
            include_content=include_content, chapter_id=chapter_id,
        )
        stats = adapter.stats()
        return {
            "blocks": blocks,
            "total_words": stats["total_words"],
            "total_blocks": stats["total_blocks"],
            "chapters": stats.get("chapters", []),
        }

    def get_block(self, project_id: str, block_id: str) -> dict[str, Any] | None:
        return self._adapter(project_id).get_block(block_id)

    def update_block(self, project_id: str, block_id: str, **kwargs: Any) -> dict[str, Any]:
        adapter = self._adapter(project_id)
        adapter.update_block(block_id, **kwargs)
        return adapter.get_block(block_id) or {}

    def delete_block(self, project_id: str, block_id: str) -> None:
        self._adapter(project_id).delete_block(block_id)

    def reorder(self, project_id: str, block_ids: list[str]) -> None:
        self._adapter(project_id).reorder(block_ids)

    def tag_blocks(self, project_id: str, block_ids: list[str], chapter_tag: str) -> int:
        return self._adapter(project_id).tag_blocks(block_ids, chapter_tag)

    def move_block(
        self, project_id: str, block_id: str,
        target_chapter_id: str | None,
    ) -> dict[str, Any]:
        """Move a manuscript block to a different chapter (or unassign)."""
        adapter = self._adapter(project_id)
        adapter.move_to_chapter(block_id, target_chapter_id)
        return adapter.get_block(block_id) or {}

    def get_stats(self, project_id: str) -> dict[str, Any]:
        return self._adapter(project_id).stats()

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_text(self, project_id: str, fmt: str = "txt") -> str:
        adapter = self._adapter(project_id)
        text = adapter.export_text()
        if fmt == "md":
            # Insert chapter headings where chapter changes
            blocks = adapter.list_blocks(include_content=True)
            # Build chapter_id -> title lookup
            stats = adapter.stats()
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

    async def _extract_metadata_async(
        self, project_id: str, block_id: str, content: str,
    ) -> None:
        """Best-effort metadata extraction -- never raises."""
        try:
            await asyncio.to_thread(self._extract_metadata, project_id, block_id, content)
        except Exception:
            logger.warning(
                "Manuscript metadata extraction failed for block %s",
                block_id, exc_info=True,
            )

    def _extract_metadata_safe(
        self, project_id: str, block_id: str, content: str,
    ) -> None:
        """Sync best-effort metadata extraction -- kept for backward compat."""
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

        adapter = self._adapter(project_id)

        # Get previous block summary for context
        blocks = adapter.list_blocks(include_content=False)
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

        adapter.update_block(
            block_id,
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
        return self._entity_repo().resolve_entity_id(project_id, name)
