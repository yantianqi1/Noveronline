"""长期记忆审核服务。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .agent_memory_stores import LongTermMemoryStore


class ArchiveMemoryReviewService:
    def __init__(self, store: Optional[LongTermMemoryStore] = None):
        self.store = store or LongTermMemoryStore()

    def list_memory(
        self,
        archive_id: str,
        include_candidates: bool = True,
        layers: Optional[tuple[str, ...]] = None,
        statuses: tuple[str, ...] = ("active",),
    ) -> Dict[str, Any]:
        resolved_layers = layers or (("canon", "candidate") if include_candidates else ("canon",))
        items = self.store.list_active_memories(archive_id, layers=resolved_layers, limit=100, statuses=statuses)
        canon_count = sum(1 for item in items if item["memory_layer"] == "canon")
        candidate_count = sum(1 for item in items if item["memory_layer"] == "candidate")
        return {
            "archive_id": archive_id,
            "items": items,
            "count": len(items),
            "canon_count": canon_count,
            "candidate_count": candidate_count,
        }

    def timeline(self, archive_id: str, memory_id: str = "", normalized_subject: str = "") -> Dict[str, Any]:
        return self.store.list_memory_timeline(
            archive_id=archive_id,
            memory_id=memory_id,
            normalized_subject=normalized_subject,
        )

    def adopt(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        memory = self.store.promote_to_canon(archive_id, memory_id)
        return {"archive_id": archive_id, "memory": memory}

    def reject(self, archive_id: str, memory_id: str) -> Dict[str, Any]:
        memory = self.store.reject_candidate(archive_id, memory_id)
        return {"archive_id": archive_id, "memory": memory}
