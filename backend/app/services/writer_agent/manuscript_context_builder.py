"""Builds continuation context from manuscript blocks using a token budget."""

from __future__ import annotations

import json
import logging
from typing import Any

from ...database import get_engine
from ...repositories import ChapterRepository, EntityRepository
from ..assets.manuscript_adapter import ManuscriptAssetAdapter

logger = logging.getLogger(__name__)

# Rough chars-to-tokens ratio for Chinese text
_CHARS_PER_TOKEN = 1.7

DEFAULT_TOKEN_BUDGET = 8000

# Default budgets (write_scene / general)
TAIL_TEXT_BUDGET_RATIO = 0.25  # 25% of budget for raw tail text
SUMMARY_BUDGET_RATIO = 0.40   # 40% for summaries
THREADS_BUDGET_RATIO = 0.15   # 15% for open threads
META_BUDGET_RATIO = 0.10      # 10% for pov/location/narrative_note
# remaining 10% reserved for entity/relationship queries by the agent

# Continuation-optimized budgets -- more raw prose for tone/rhythm matching
CONT_TAIL_TEXT_BUDGET_RATIO = 0.40
CONT_SUMMARY_BUDGET_RATIO = 0.30
CONT_THREADS_BUDGET_RATIO = 0.12
CONT_META_BUDGET_RATIO = 0.08


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


_EVENTS_BUDGET_RATIO = 0.10


def _get_manuscript_adapter(project_id: str) -> ManuscriptAssetAdapter:
    """Build a ManuscriptAssetAdapter with chapter_lookup wired to ChapterRepository.

    Also used by tool_executors for manuscript search/stats.
    """
    engine = get_engine()
    chapter_repo = ChapterRepository(engine)

    def chapter_lookup(chapter_id: str | None) -> dict | None:
        if not chapter_id:
            return None
        return chapter_repo.get_chapter(project_id, chapter_id)

    return ManuscriptAssetAdapter(project_id, chapter_lookup=chapter_lookup)


def _collect_recent_events(
    entity_repo: EntityRepository,
    project_id: str,
    pov_entity_id: str,
    last_block: dict,
    token_budget: int,
) -> list[dict[str, Any]]:
    """Collect recent character events for POV and involved entities."""
    budget = int(token_budget * _EVENTS_BUDGET_RATIO)
    tokens_used = 0
    results: list[dict[str, Any]] = []

    # Gather entity IDs to query: POV first, then involved entities
    entity_ids: list[str] = []
    if pov_entity_id:
        entity_ids.append(pov_entity_id)
    try:
        involved = json.loads(last_block.get("involved_entities_json") or "[]")
        if isinstance(involved, list):
            for eid in involved:
                if eid and eid not in entity_ids:
                    entity_ids.append(str(eid))
    except (json.JSONDecodeError, TypeError):
        pass

    for eid in entity_ids[:5]:  # cap to avoid excessive queries
        try:
            events = entity_repo.get_entity_recent_events(project_id, eid, limit=3)
        except Exception:
            continue
        for ev in events:
            text = f"[{ev.get('event_type', '')}] {ev.get('summary', '')}"
            tokens = _estimate_tokens(text)
            if tokens_used + tokens > budget:
                return results
            results.append({
                "entity_id": eid,
                "event_type": ev.get("event_type", ""),
                "summary": ev.get("summary", ""),
                "chapter_order": ev.get("chapter_order", 0),
            })
            tokens_used += tokens

    return results


def build_continuation_context(
    project_id: str,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    last_block_id: str | None = None,
) -> dict[str, Any]:
    """Build continuation context from the most recent manuscript blocks.

    Args:
        project_id: The project to build context for.
        token_budget: Total token budget for the context.
        last_block_id: If provided, anchor context from this specific block
                       instead of the latest one. Useful when the frontend
                       knows exactly which block was just committed.

    Returns a dict suitable for both frontend display and LLM injection.
    """
    engine = get_engine()
    entity_repo = EntityRepository(engine)
    adapter = _get_manuscript_adapter(project_id)

    blocks = adapter.get_continuation_blocks(limit=50)

    if not blocks:
        stats = adapter.stats()
        return {
            "recent_summaries": [],
            "writing_styles": [],
            "active_threads": [],
            "last_pov": "",
            "last_location": "",
            "narrative_note": "",
            "tail_text": "",
            "total_words": stats["total_words"],
            "total_blocks": stats["total_blocks"],
            "last_block_id": "",
            "last_block_order": 0,
            "last_chapter_tag": "",
        }

    # Blocks are newest-first from DB; anchor to specific block or most recent
    last_block = blocks[0]
    if last_block_id:
        for b in blocks:
            if b.get("block_id") == last_block_id:
                last_block = b
                # Re-slice blocks: only keep this block and older ones
                anchor_order = b["block_order"]
                blocks = [blk for blk in blocks if blk["block_order"] <= anchor_order]
                break

    # Use continuation-optimized budgets (more raw prose)
    tail_ratio = CONT_TAIL_TEXT_BUDGET_RATIO
    summary_ratio = CONT_SUMMARY_BUDGET_RATIO
    threads_ratio = CONT_THREADS_BUDGET_RATIO

    # --- Tail text (raw prose from anchor block) ---
    tail_budget = int(token_budget * tail_ratio)
    tail_chars = int(tail_budget * _CHARS_PER_TOKEN)
    content = last_block.get("content", "")
    tail_text = content[-tail_chars:] if len(content) > tail_chars else content

    # --- Summaries (walk backwards) ---
    summary_budget = int(token_budget * summary_ratio)
    summaries: list[dict[str, Any]] = []
    summary_tokens_used = 0
    for block in blocks:
        summary = block.get("summary") or ""
        if not summary:
            continue
        tokens = _estimate_tokens(summary)
        if summary_tokens_used + tokens > summary_budget:
            break
        summaries.append({
            "block_order": block["block_order"],
            "chapter_id": block.get("chapter_id", ""),
            "chapter_tag": block.get("chapter_tag", ""),
            "summary": summary,
        })
        summary_tokens_used += tokens

    # Reverse so they're in chronological order
    summaries.reverse()

    # --- Open threads (aggregate + deduplicate) ---
    threads_budget = int(token_budget * threads_ratio)
    seen_threads: set[str] = set()
    active_threads: list[str] = []
    threads_tokens_used = 0
    for block in blocks:
        raw = block.get("open_threads_json")
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, list):
                continue
        except (json.JSONDecodeError, TypeError):
            continue
        for t in parsed:
            t_str = str(t).strip()
            if t_str and t_str not in seen_threads:
                tokens = _estimate_tokens(t_str)
                if threads_tokens_used + tokens > threads_budget:
                    break
                seen_threads.add(t_str)
                active_threads.append(t_str)
                threads_tokens_used += tokens

    # --- Metadata from last block ---
    last_pov = last_block.get("pov_entity_id") or ""
    last_location = last_block.get("location") or ""
    narrative_note = last_block.get("narrative_note") or ""

    # --- Recent character events (use reserved 10% budget) ---
    recent_character_events = _collect_recent_events(
        entity_repo, project_id, last_pov, last_block, token_budget,
    )

    stats = adapter.stats()

    # --- Enabled writing_style assets (global + project), if any ---
    writing_styles: list[dict[str, Any]] = []
    try:
        from ..assets.assets_service import AssetsService
        assets_svc = AssetsService()
        for s in assets_svc.list_merged(
            project_id=project_id,
            asset_type="writing_style",
            enabled_only=True,
            limit=10,
        ):
            writing_styles.append({
                "asset_id": s["asset_id"],
                "title": s.get("title", ""),
                "category": s.get("category", ""),
                "summary": s.get("summary", ""),
                "content": s.get("content", ""),
            })
    except Exception:
        logger.warning("failed to load writing_style assets", exc_info=True)

    return {
        "recent_summaries": summaries,
        "writing_styles": writing_styles,
        "active_threads": active_threads,
        "last_pov": last_pov,
        "last_location": last_location,
        "narrative_note": narrative_note,
        "tail_text": tail_text,
        "recent_character_events": recent_character_events,
        "total_words": stats["total_words"],
        "total_blocks": stats["total_blocks"],
        "last_block_id": last_block.get("block_id", ""),
        "last_block_order": last_block.get("block_order", 0),
        "last_chapter_id": last_block.get("chapter_id", ""),
        "last_chapter_tag": last_block.get("chapter_tag", ""),
    }
