"""Builds continuation context from manuscript blocks using a token budget."""

from __future__ import annotations

import json
import logging
from typing import Any

from .novel_db import NovelDB

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

# Continuation-optimized budgets — more raw prose for tone/rhythm matching
CONT_TAIL_TEXT_BUDGET_RATIO = 0.40
CONT_SUMMARY_BUDGET_RATIO = 0.30
CONT_THREADS_BUDGET_RATIO = 0.12
CONT_META_BUDGET_RATIO = 0.08


def _estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, int(len(text) / _CHARS_PER_TOKEN))


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
    db = NovelDB()
    blocks = db.get_manuscript_continuation_blocks(project_id, limit=50)

    if not blocks:
        stats = db.get_manuscript_stats(project_id)
        return {
            "recent_summaries": [],
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

    stats = db.get_manuscript_stats(project_id)

    return {
        "recent_summaries": summaries,
        "active_threads": active_threads,
        "last_pov": last_pov,
        "last_location": last_location,
        "narrative_note": narrative_note,
        "tail_text": tail_text,
        "total_words": stats["total_words"],
        "total_blocks": stats["total_blocks"],
        "last_block_id": last_block.get("block_id", ""),
        "last_block_order": last_block.get("block_order", 0),
        "last_chapter_tag": last_block.get("chapter_tag", ""),
    }
