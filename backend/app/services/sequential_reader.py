"""
SequentialReader — drives sequential novel reading via LLM analysis.

Reads segments one by one, merges results into a ReadingNotesManager,
and triggers arc/volume summaries at configured intervals.

Resilience (无感自动重试):
  L0  — built into LLMClient: 3 transient HTTP attempts + 3 JSON-parse attempts.
  L1  — per-call retry via ``retry_policy.retry_with_policy``, degrading prompt
        on the 2nd attempt (lower temperature, smaller max_tokens).
  L2  — if consecutive segments exhaust L1, inject a stage cooldown before
        continuing (mitigate rate-limit storms).
  L3  — after the main loop, sweep segments still marked retry_needed with a
        minimal prompt for last-chance recovery.
  L-  — ``PermanentLLMError`` (auth/quota/model-not-found) propagates up so
        the runner marks the stage FAILED without burning the retry budget.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from .reading_notes_manager import ReadingNotesManager
from .sequential_reader_prompts import (
    build_arc_summary_prompt,
    build_segment_reading_prompt,
    build_volume_summary_prompt,
)
from ..utils.llm_json import normalize_json_object
from ..utils.retry_policy import (
    ExhaustedLLMRetries,
    PermanentLLMError,
    RetryPolicy,
    retry_with_policy,
)

logger = logging.getLogger(__name__)

MODULE_KEY = "sequential_reading"

# Phase E-1: bump segment cap from 8192 → 12288. The full schema (segment_summary
# + character_updates + relationship_changes + co_occurrence + organization_dynamics
# + location_state_changes + plot_threads + world_building + consistency_notes
# + narrative_phase) routinely lands close to 8 K on dialogue-dense passages, and
# truncation drops the *tail* fields (world_building / consistency_notes /
# narrative_phase) silently. The headroom costs little since most segments still
# return well under 6 K; the retry-degraded prompt halves the cap on attempt 1.
_MAX_TOKENS_SEGMENT = 12288
_MAX_TOKENS_ARC = 4096
_MAX_TOKENS_VOLUME = 6144
_MAX_TOKENS_SWEEP = 2048


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
    retry_policy:
        L1 retry policy for a single LLM call. Defaults to ``RetryPolicy()``
        (2 attempts total, 10s initial backoff, 30s max).
    cooldown_streak / cooldown_seconds:
        L2 fuse — after N consecutive exhausted retries, pause the stage for
        ``cooldown_seconds`` before continuing. Set cooldown_seconds=0 to
        disable.
    sweep_enabled:
        L3 — attempt a minimal-prompt pass over still-failed segments at the
        end of the main loop.
    """

    def __init__(
        self,
        llm_router=None,
        arc_interval: int = 5,
        volume_arc_threshold: int = 10,
        retry_policy: Optional[RetryPolicy] = None,
        cooldown_streak: int = 3,
        cooldown_seconds: float = 30.0,
        sweep_enabled: bool = True,
    ) -> None:
        self.llm_router = llm_router
        self.arc_interval = arc_interval
        self.volume_arc_threshold = volume_arc_threshold
        self.retry_policy = retry_policy or RetryPolicy()
        self.cooldown_streak = max(1, cooldown_streak)
        self.cooldown_seconds = max(0.0, cooldown_seconds)
        self.sweep_enabled = sweep_enabled

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(
        self,
        segments: Sequence[Dict],
        use_llm: bool = True,
        progress_callback: Optional[Callable[[str, Dict], None]] = None,
        cancel_check: Optional[Callable[[], None]] = None,
        checkpoint_callback: Optional[Callable[[ReadingNotesManager], None]] = None,
        checkpoint_every: int = 5,
    ) -> ReadingNotesManager:
        """Read all segments sequentially.

        Parameters
        ----------
        segments:
            List of segment dicts as produced by SmartNovelSegmenter.
        use_llm:
            When False, runs offline mode (minimal notes from chapter titles).
        progress_callback:
            Called with (event_type, data). Event types:
              - ``segment_start`` / ``segment_end``
                data: {segment_id, segment_index, total_segments}
              - ``arc_start`` / ``arc_end``
                data: {arc_id, arc_index, segment_count?}
              - ``volume_start`` / ``volume_end``
                data: {volume_id, volume_index, arc_count?}
              - ``segment_retry`` (new, silent UI)
                data: {segment_id, attempt, max_attempts, wait_seconds, error_class, reason, scope?}
              - ``stage_cooldown`` (new, silent UI)
                data: {wait_seconds, failed_streak}
              - ``segment_permanent_failure`` (new, warning-level UI)
                data: {segment_id, error_class, error_detail, scope?}
              - ``segment_sweep_recovered`` (new, debug only)
                data: {segment_id}
        checkpoint_callback:
            If set, called with the ``ReadingNotesManager`` every
            ``checkpoint_every`` completed segments. Used by the runner to
            persist ``reading_notes.json`` periodically so that 断点续传 can
            resume even when the task gets killed mid-flight.
        checkpoint_every:
            Segment cadence for ``checkpoint_callback``. Defaults to 5.
            Ignored when ``checkpoint_callback`` is None.

        Returns
        -------
        ReadingNotesManager
            Completed reading notes. Segments whose LLM call could not be
            recovered are persisted with ``status="retry_needed"`` so the
            manual retry endpoint can pick them up later.
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
        consecutive_failures = 0
        cadence = max(1, int(checkpoint_every))

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

            consecutive_failures = self._read_one_segment(
                client, manager, segment, segment_id,
                progress_callback, consecutive_failures,
            )

            if manager.needs_arc_summary():
                self._generate_arc_summary(client, manager, progress_callback)

            if manager.needs_volume_summary():
                self._generate_volume_summary(client, manager, progress_callback)

            if progress_callback:
                progress_callback("segment_end", {
                    "segment_id": segment_id,
                    "segment_index": idx,
                    "total_segments": total,
                })

            # Periodic checkpoint — keep 断点续传 viable even if the process
            # is killed mid-flight. Failures in the callback must not abort
            # the read loop (a transient write issue should be retried on
            # the next tick, not crash the whole task).
            if checkpoint_callback and (idx + 1) % cadence == 0:
                try:
                    checkpoint_callback(manager)
                except Exception:
                    logger.exception(
                        "reading_notes checkpoint 失败（segment %s/%s）",
                        idx + 1, total,
                    )

        # L3 — sweep remaining failures with a conservative last-chance pass
        if self.sweep_enabled:
            self._sweep_failed_segments(client, manager, segments, progress_callback)

        # Final arc summary for any trailing segments
        if manager.pending_arc_segments():
            self._generate_arc_summary(client, manager, progress_callback)

        return manager

    # ------------------------------------------------------------------
    # Segment handling
    # ------------------------------------------------------------------

    def _read_one_segment(
        self,
        client: Any,
        manager: ReadingNotesManager,
        segment: Dict,
        segment_id: str,
        progress_callback: Optional[Callable[[str, Dict], None]],
        consecutive_failures: int,
    ) -> int:
        """Read one segment with L1+L2 retry. Returns updated failure streak."""
        context = manager.assemble_context()
        segment_text = self._extract_segment_text(segment)
        known_entities = manager.canonical_entity_table()

        def call(attempt: int) -> Dict[str, Any]:
            if attempt == 0:
                temperature, max_tokens = 0.3, _MAX_TOKENS_SEGMENT
            else:
                temperature, max_tokens = 0.2, max(_MAX_TOKENS_SEGMENT // 2, 2048)
            messages = build_segment_reading_prompt(
                context, segment_text, known_entities=known_entities,
            )
            raw = client.chat_json_value(
                messages, temperature=temperature, max_tokens=max_tokens,
            )
            return normalize_json_object(raw, f"segment {segment_id}")

        def on_retry(attempt, max_attempts, wait_seconds, error_class, exc):
            if progress_callback:
                progress_callback("segment_retry", {
                    "segment_id": segment_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "wait_seconds": wait_seconds,
                    "error_class": error_class,
                    "reason": str(exc)[:200],
                    "scope": "segment",
                })

        try:
            result = retry_with_policy(
                call, policy=self.retry_policy, on_retry=on_retry,
            )
        except PermanentLLMError:
            # Let the runner mark the stage FAILED — no point burning budget.
            raise
        except ExhaustedLLMRetries as exc:
            logger.warning(
                "Segment %s exhausted L1 retries after %d attempts: %s",
                segment_id, exc.attempts, exc.detail,
            )
            manager.add_segment_summary(
                segment_id, "",
                status="retry_needed",
                error_class=exc.error_class,
                error_detail=exc.detail[:500],
            )
            if progress_callback:
                progress_callback("segment_permanent_failure", {
                    "segment_id": segment_id,
                    "error_class": exc.error_class,
                    "error_detail": exc.detail[:500],
                    "scope": "segment",
                })
            consecutive_failures += 1
            if (
                consecutive_failures >= self.cooldown_streak
                and self.cooldown_seconds > 0
            ):
                if progress_callback:
                    progress_callback("stage_cooldown", {
                        "wait_seconds": self.cooldown_seconds,
                        "failed_streak": consecutive_failures,
                    })
                time.sleep(self.cooldown_seconds)
                consecutive_failures = 0
            return consecutive_failures

        # Success path.
        self._merge_segment_result(manager, result, segment_id)
        return 0

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    def _merge_segment_result(
        self,
        manager: ReadingNotesManager,
        result: Dict[str, Any],
        segment_id: str,
    ) -> None:
        """Merge LLM JSON output into the notes manager (includes summary)."""
        summary = result.get("segment_summary", "")
        manager.add_segment_summary(segment_id, summary)
        self._merge_structured_fields(manager, result, segment_id)

    def _merge_structured_fields(
        self,
        manager: ReadingNotesManager,
        result: Dict[str, Any],
        segment_id: str,
    ) -> None:
        """Merge non-summary fields only — used by sweep / manual-retry paths."""
        character_updates = result.get("character_updates", [])
        if character_updates:
            manager.merge_character_updates(character_updates, segment_id)

        relationship_changes = result.get("relationship_changes", [])
        if relationship_changes:
            manager.merge_relationship_changes(relationship_changes, segment_id)

        co_occurrence = result.get("co_occurrence", [])
        if co_occurrence:
            manager.merge_co_occurrence(co_occurrence, segment_id)

        org_dynamics = result.get("organization_dynamics", [])
        if org_dynamics:
            manager.merge_organization_dynamics(org_dynamics, segment_id)

        loc_changes = result.get("location_state_changes", [])
        if loc_changes:
            manager.merge_location_state_changes(loc_changes, segment_id)

        plot_threads = result.get("plot_threads", [])
        if plot_threads:
            manager.merge_plot_threads(plot_threads, segment_id)

        world_building = result.get("world_building", [])
        if world_building:
            manager.merge_world_building(world_building)

        consistency_notes = result.get("consistency_notes", [])
        if consistency_notes:
            manager.merge_consistency_notes(consistency_notes, segment_id)

        narrative_phase = result.get("narrative_phase", "")
        if narrative_phase:
            manager.update_narrative_phase(narrative_phase)

    # ------------------------------------------------------------------
    # Sweep (L3)
    # ------------------------------------------------------------------

    def _sweep_failed_segments(
        self,
        client: Any,
        manager: ReadingNotesManager,
        segments: Sequence[Dict],
        progress_callback: Optional[Callable[[str, Dict], None]],
    ) -> None:
        """Last-chance pass for still-failed segments with minimal prompt."""
        failed_ids = list(manager.failed_segment_ids())
        if not failed_ids:
            return
        segments_by_id = {
            seg.get("segment_id", f"seg_{idx + 1:03d}"): seg
            for idx, seg in enumerate(segments)
        }
        for segment_id in failed_ids:
            seg = segments_by_id.get(segment_id)
            if not seg:
                continue
            text = self._extract_segment_text(seg)
            try:
                messages = build_segment_reading_prompt("", text)
                raw = client.chat_json_value(
                    messages, temperature=0.2, max_tokens=_MAX_TOKENS_SWEEP,
                )
                result = normalize_json_object(raw, f"segment {segment_id} (sweep)")
            except PermanentLLMError:
                raise
            except Exception as exc:
                logger.warning("L3 sweep for %s also failed: %s", segment_id, exc)
                continue

            summary = result.get("segment_summary", "") if isinstance(result, dict) else ""
            if not summary:
                continue
            if manager.update_segment_summary(segment_id, summary):
                self._merge_structured_fields(manager, result, segment_id)
                if progress_callback:
                    progress_callback("segment_sweep_recovered", {
                        "segment_id": segment_id,
                    })

    # ------------------------------------------------------------------
    # Arc / volume summaries
    # ------------------------------------------------------------------

    def _generate_arc_summary(
        self,
        client: Any,
        manager: ReadingNotesManager,
        progress_callback: Optional[Callable[[str, Dict], None]] = None,
        pending: Optional[List[Dict]] = None,
    ) -> None:
        """Generate an arc summary from pending segments and record it.

        ``pending`` overrides ``manager.pending_arc_segments()`` — used by the
        retry backfill path to generate arc_interval-sized chunks even when a
        large batch of segments becomes uncovered at once.
        """
        if pending is None:
            pending = manager.pending_arc_segments()
        if not pending:
            return

        arc_index = len(manager.notes["plot_state"]["arc_summaries"]) + 1
        arc_id = f"arc_{arc_index:03d}"
        core_context = manager.assemble_context()

        if progress_callback:
            progress_callback("arc_start", {
                "arc_id": arc_id,
                "arc_index": arc_index,
                "segment_count": len(pending),
            })

        def call(attempt: int) -> Dict[str, Any]:
            if attempt == 0:
                temperature, max_tokens = 0.3, _MAX_TOKENS_ARC
            else:
                temperature, max_tokens = 0.2, max(_MAX_TOKENS_ARC // 2, 2048)
            messages = build_arc_summary_prompt(core_context, pending)
            raw = client.chat_json_value(
                messages, temperature=temperature, max_tokens=max_tokens,
            )
            return normalize_json_object(raw, f"arc {arc_id}")

        def on_retry(attempt, max_attempts, wait_seconds, error_class, exc):
            if progress_callback:
                progress_callback("segment_retry", {
                    "segment_id": arc_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "wait_seconds": wait_seconds,
                    "error_class": error_class,
                    "reason": str(exc)[:200],
                    "scope": "arc",
                })

        try:
            result = retry_with_policy(
                call, policy=self.retry_policy, on_retry=on_retry,
            )
        except PermanentLLMError:
            if progress_callback:
                progress_callback("arc_end", {"arc_id": arc_id, "arc_index": arc_index})
            raise
        except ExhaustedLLMRetries as exc:
            logger.warning("Arc %s exhausted retries: %s", arc_id, exc.detail)
            manager.add_arc_summary(
                arc_id, "", pending,
                status="retry_needed",
                error_class=exc.error_class,
                error_detail=exc.detail[:500],
            )
            if progress_callback:
                progress_callback("segment_permanent_failure", {
                    "segment_id": arc_id,
                    "error_class": exc.error_class,
                    "error_detail": exc.detail[:500],
                    "scope": "arc",
                })
                progress_callback("arc_end", {"arc_id": arc_id, "arc_index": arc_index})
            return

        arc_summary_text = result.get("arc_summary", "")
        manager.add_arc_summary(arc_id, arc_summary_text, pending)
        self._merge_arc_structured_fields(manager, result, arc_id)
        if progress_callback:
            progress_callback("arc_end", {"arc_id": arc_id, "arc_index": arc_index})

    def _merge_arc_structured_fields(
        self,
        manager: ReadingNotesManager,
        result: Dict[str, Any],
        arc_id: str,
    ) -> None:
        key_events = result.get("key_events", [])
        if key_events:
            manager.merge_key_events(key_events, arc_id)

        for ca in result.get("character_arcs", []):
            name = ca.get("name", "")
            change = ca.get("change", "")
            if name and change:
                chars = manager.notes["core_facts"]["characters"]
                if name in chars:
                    chars[name].setdefault("key_actions", []).append(f"[弧线变化] {change}")

        for rs in result.get("relationship_shifts", []):
            src = rs.get("source", "")
            tgt = rs.get("target", "")
            shift = rs.get("shift", "")
            if src and tgt and shift:
                manager.notes["relationship_graph"].append({
                    "source": src, "target": tgt,
                    "relation": shift, "trigger": f"弧线 {arc_id}",
                    "evidence": "", "segment_id": arc_id,
                })

        for rule in result.get("world_rules_introduced", []):
            if rule:
                manager.merge_world_building([{"fact": rule, "evidence": f"弧线 {arc_id}"}])

    def _generate_volume_summary(
        self,
        client: Any,
        manager: ReadingNotesManager,
        progress_callback: Optional[Callable[[str, Dict], None]] = None,
    ) -> None:
        """Generate a volume summary from all arc summaries and record it."""
        arc_summaries = manager.notes["plot_state"]["arc_summaries"]
        if not arc_summaries:
            return

        volume_index = len(manager.notes["plot_state"]["volume_summaries"]) + 1
        volume_id = f"vol_{volume_index:03d}"

        if progress_callback:
            progress_callback("volume_start", {
                "volume_id": volume_id,
                "volume_index": volume_index,
                "arc_count": len(arc_summaries),
            })

        def call(attempt: int) -> Dict[str, Any]:
            if attempt == 0:
                temperature, max_tokens = 0.3, _MAX_TOKENS_VOLUME
            else:
                temperature, max_tokens = 0.2, max(_MAX_TOKENS_VOLUME // 2, 2048)
            messages = build_volume_summary_prompt(arc_summaries)
            raw = client.chat_json_value(
                messages, temperature=temperature, max_tokens=max_tokens,
            )
            return normalize_json_object(raw, f"volume {volume_id}")

        def on_retry(attempt, max_attempts, wait_seconds, error_class, exc):
            if progress_callback:
                progress_callback("segment_retry", {
                    "segment_id": volume_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "wait_seconds": wait_seconds,
                    "error_class": error_class,
                    "reason": str(exc)[:200],
                    "scope": "volume",
                })

        covered_arc_ids = [a["arc_id"] for a in arc_summaries]
        try:
            result = retry_with_policy(
                call, policy=self.retry_policy, on_retry=on_retry,
            )
        except PermanentLLMError:
            if progress_callback:
                progress_callback("volume_end", {"volume_id": volume_id, "volume_index": volume_index})
            raise
        except ExhaustedLLMRetries as exc:
            logger.warning("Volume %s exhausted retries: %s", volume_id, exc.detail)
            manager.add_volume_summary(
                volume_id, "", covered_arc_ids,
                status="retry_needed",
                error_class=exc.error_class,
                error_detail=exc.detail[:500],
            )
            if progress_callback:
                progress_callback("segment_permanent_failure", {
                    "segment_id": volume_id,
                    "error_class": exc.error_class,
                    "error_detail": exc.detail[:500],
                    "scope": "volume",
                })
                progress_callback("volume_end", {"volume_id": volume_id, "volume_index": volume_index})
            return

        volume_summary_text = result.get("volume_summary", "")
        manager.add_volume_summary(
            volume_id,
            volume_summary_text,
            covered_arc_ids,
            theme=(result.get("theme") or "") or None,
            main_arcs=result.get("main_arcs") or None,
            faction_changes=result.get("faction_changes") or None,
            cross_volume_threads=result.get("cross_volume_threads") or None,
        )
        if progress_callback:
            progress_callback("volume_end", {"volume_id": volume_id, "volume_index": volume_index})

    # ------------------------------------------------------------------
    # Offline / helpers
    # ------------------------------------------------------------------

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
