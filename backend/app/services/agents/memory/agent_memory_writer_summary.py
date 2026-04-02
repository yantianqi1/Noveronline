"""把运行时记忆整理成写作摘要。"""

from __future__ import annotations

from typing import Any, Dict, List

WRITER_MEMORY_BUCKET_LIMIT = 3
PRIORITY_TYPES = {"promise": 0, "strategy": 1, "relationship": 2, "goal": 3, "preference": 4, "fact": 5}


def build_writer_memory_summary(
    session_items: List[Dict[str, Any]],
    canon_items: List[Dict[str, Any]],
    candidate_items: List[Dict[str, Any]],
    include_candidates: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    ordered = list(session_items) + list(canon_items)
    if include_candidates:
        ordered.extend(candidate_items)
    ordered.sort(key=_sort_key)
    summary = {
        "recent_commitments": [],
        "active_strategies": [],
        "relationship_tensions": [],
        "identity_constraints": [],
    }
    for item in ordered:
        bucket = _bucket_name(item.get("memory_type", "fact"))
        if len(summary[bucket]) >= WRITER_MEMORY_BUCKET_LIMIT:
            continue
        summary[bucket].append(
            {
                "memory_id": item["memory_id"],
                "archive_id": item.get("archive_id", ""),
                "memory_type": item.get("memory_type", "fact"),
                "summary": item.get("summary", ""),
                "source_scope": item.get("scope", "session"),
                "memory_layer": item.get("memory_layer", "canon"),
                "normalized_subject": item.get("normalized_subject", ""),
                "salience": float(item.get("salience") or 0.0),
            }
        )
    return summary


def _sort_key(item: Dict[str, Any]) -> tuple[int, int, float]:
    memory_type = item.get("memory_type", "fact")
    scope_order = 0 if item.get("scope") == "session" else 1
    return (
        PRIORITY_TYPES.get(memory_type, 9),
        scope_order,
        -float(item.get("salience") or 0.0),
    )


def _bucket_name(memory_type: str) -> str:
    if memory_type == "promise":
        return "recent_commitments"
    if memory_type in {"strategy", "goal"}:
        return "active_strategies"
    if memory_type == "relationship":
        return "relationship_tensions"
    return "identity_constraints"
