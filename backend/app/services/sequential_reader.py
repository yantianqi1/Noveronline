"""
SequentialReader — drives sequential novel reading via LLM analysis.

Reads segments one by one, merges results into a ReadingNotesManager,
and triggers arc/volume summaries at configured intervals.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional, Sequence

from .reading_notes_manager import ReadingNotesManager
from .sequential_reader_prompts import (
    build_arc_summary_prompt,
    build_segment_reading_prompt,
    build_volume_summary_prompt,
)

logger = logging.getLogger(__name__)

MODULE_KEY = "sequential_reading"


class SequentialReader:
    """Reads novel segments sequentially, maintaining running notes.

    Parameters
    ----------
    llm_router:
        Object with a ``build_client(module_key)`` method returning an
        LLMClient (must have ``chat_json_value``).  Required when
        ``use_llm=True``.
    arc_interval:
        Number of segments between arc-summary generations.
    volume_arc_threshold:
        Number of arcs that triggers a volume-summary generation.
    """

    def __init__(
        self,
        llm_router=None,
        arc_interval: int = 5,
        volume_arc_threshold: int = 10,
    ) -> None:
        self.llm_router = llm_router
        self.arc_interval = arc_interval
        self.volume_arc_threshold = volume_arc_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(
        self,
        segments: Sequence[Dict],
        use_llm: bool = True,
        progress_callback: Optional[Callable[[str, Dict], None]] = None,
        cancel_check: Optional[Callable[[], None]] = None,
    ) -> ReadingNotesManager:
        """Read all segments sequentially.

        Parameters
        ----------
        segments:
            List of segment dicts as produced by SmartNovelSegmenter.
        use_llm:
            When False, runs offline mode (minimal notes from chapter titles).
        progress_callback:
            Called with (event_type, data) at segment start/end.
            event_type: "segment_start" | "segment_end"
            data keys: segment_id, segment_index, total_segments

        Returns
        -------
        ReadingNotesManager
            Completed reading notes.
        """
        manager = ReadingNotesManager(
            arc_interval=self.arc_interval,
            volume_arc_threshold=self.volume_arc_threshold,
        )

        if not use_llm:
            self._offline_read(segments, manager, progress_callback)
            return manager

        client = self.llm_router.build_client(MODULE_KEY)
        total = len(segments)

        for idx, segment in enumerate(segments):
            segment_id = segment.get("segment_id", f"seg_{idx + 1:03d}")

            if cancel_check is not None:
                cancel_check()

            if progress_callback:
                progress_callback("segment_start", {
                    "segment_id": segment_id,
                    "segment_index": idx,
                    "total_segments": total,
                })

            context = manager.assemble_context()
            segment_text = self._extract_segment_text(segment)
            messages = build_segment_reading_prompt(context, segment_text)

            try:
                result = client.chat_json_value(messages, temperature=0.3, max_tokens=8192)
                self._merge_segment_result(manager, result, segment_id)
            except Exception:
                logger.exception("LLM error on segment %s; skipping merge", segment_id)
                manager.add_segment_summary(segment_id, f"[分析失败] {segment_id}")

            if manager.needs_arc_summary():
                self._generate_arc_summary(client, manager)

            if manager.needs_volume_summary():
                self._generate_volume_summary(client, manager)

            if progress_callback:
                progress_callback("segment_end", {
                    "segment_id": segment_id,
                    "segment_index": idx,
                    "total_segments": total,
                })

        # Final arc summary for any trailing segments
        if manager.pending_arc_segments():
            self._generate_arc_summary(client, manager)

        return manager

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _merge_segment_result(
        self,
        manager: ReadingNotesManager,
        result: Dict[str, Any],
        segment_id: str,
    ) -> None:
        """Merge LLM JSON output into the notes manager."""
        summary = result.get("segment_summary", "")
        manager.add_segment_summary(segment_id, summary)

        character_updates = result.get("character_updates", [])
        if character_updates:
            manager.merge_character_updates(character_updates, segment_id)

        relationship_changes = result.get("relationship_changes", [])
        if relationship_changes:
            manager.merge_relationship_changes(relationship_changes, segment_id)

        plot_threads = result.get("plot_threads", [])
        if plot_threads:
            manager.merge_plot_threads(plot_threads)

        world_building = result.get("world_building", [])
        if world_building:
            manager.merge_world_building(world_building)

        narrative_phase = result.get("narrative_phase", "")
        if narrative_phase:
            manager.update_narrative_phase(narrative_phase)

    def _generate_arc_summary(
        self,
        client: Any,
        manager: ReadingNotesManager,
    ) -> None:
        """Generate an arc summary from pending segments and record it."""
        pending = manager.pending_arc_segments()
        if not pending:
            return

        arc_index = len(manager.notes["plot_state"]["arc_summaries"]) + 1
        arc_id = f"arc_{arc_index:03d}"

        core_context = manager.assemble_context()
        messages = build_arc_summary_prompt(core_context, pending)

        try:
            result = client.chat_json_value(messages, temperature=0.3, max_tokens=4096)
            arc_summary_text = result.get("arc_summary", "")
        except Exception:
            logger.exception("LLM error generating arc summary %s", arc_id)
            arc_summary_text = f"[弧线摘要生成失败] {arc_id}"

        manager.add_arc_summary(arc_id, arc_summary_text, pending)

    def _generate_volume_summary(
        self,
        client: Any,
        manager: ReadingNotesManager,
    ) -> None:
        """Generate a volume summary from all arc summaries and record it."""
        arc_summaries = manager.notes["plot_state"]["arc_summaries"]
        if not arc_summaries:
            return

        volume_index = len(manager.notes["plot_state"]["volume_summaries"]) + 1
        volume_id = f"vol_{volume_index:03d}"

        messages = build_volume_summary_prompt(arc_summaries)

        try:
            result = client.chat_json_value(messages, temperature=0.3, max_tokens=6144)
            volume_summary_text = result.get("volume_summary", "")
        except Exception:
            logger.exception("LLM error generating volume summary %s", volume_id)
            volume_summary_text = f"[卷摘要生成失败] {volume_id}"

        covered_arc_ids = [a["arc_id"] for a in arc_summaries]
        manager.add_volume_summary(volume_id, volume_summary_text, covered_arc_ids)

    def _offline_read(
        self,
        segments: Sequence[Dict],
        manager: ReadingNotesManager,
        progress_callback: Optional[Callable[[str, Dict], None]],
    ) -> None:
        """Offline mode: produce minimal notes from chapter titles only."""
        total = len(segments)
        for idx, segment in enumerate(segments):
            segment_id = segment.get("segment_id", f"seg_{idx + 1:03d}")

            if progress_callback:
                progress_callback("segment_start", {
                    "segment_id": segment_id,
                    "segment_index": idx,
                    "total_segments": total,
                })

            titles = [
                ch.get("title", f"章节{i + 1}")
                for i, ch in enumerate(segment.get("chapters", []))
            ]
            summary = f"[离线] 段落 {segment_id}，含章节：{', '.join(titles)}"
            manager.add_segment_summary(segment_id, summary)

            if progress_callback:
                progress_callback("segment_end", {
                    "segment_id": segment_id,
                    "segment_index": idx,
                    "total_segments": total,
                })

    def _extract_segment_text(self, segment: Dict) -> str:
        """Join chapter contents with their titles into a single text block."""
        parts: List[str] = []
        for chapter in segment.get("chapters", []):
            title = chapter.get("title", "")
            content = chapter.get("content", "")
            if title:
                parts.append(f"【{title}】\n{content}")
            else:
                parts.append(content)
        return "\n\n".join(parts)
