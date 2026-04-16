"""故事记忆聚合服务。"""

from typing import Any, Dict, List, Sequence, Tuple


MAX_SNAPSHOT_SUMMARY = 2000
RECENT_BLOCK_LIMIT = 3
RELEVANT_ITEM_LIMIT = 12
FINGERPRINT_BLOCK_LIMIT = 2


class StoryMemoryBuilder:
    """按块顺序合并局部事实，生成全局记忆与块前快照。"""

    def build(
        self,
        packets: Sequence[Dict[str, Any]],
        blocks: Sequence[Dict[str, Any]] = (),
        anchors: Sequence[Dict[str, Any]] = (),
        skeleton: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        ordered_packets = sorted(packets, key=lambda item: item["block_id"])
        block_map = {block["block_id"]: block for block in blocks}
        sketch_map = {item["chapter_id"]: item for item in (skeleton or {}).get("chapter_sketches", [])}
        limits = self._adaptive_limits(len(ordered_packets))
        relationship_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        entity_registry: Dict[str, Dict[str, Any]] = {}
        open_thread_map: Dict[str, Dict[str, Any]] = {}
        block_summaries: List[Dict[str, Any]] = []
        event_timeline: List[Dict[str, Any]] = []
        alias_map: Dict[str, str] = {}
        world_rules: List[str] = []
        snapshots = []

        for packet in ordered_packets:
            snapshots.append(
                self._snapshot(
                    packet["block_id"],
                    block_summaries,
                    entity_registry,
                    relationship_map,
                    open_thread_map,
                    alias_map,
                    limits,
                    block_map,
                    anchors,
                    sketch_map,
                )
            )
            self._merge_packet(
                packet,
                entity_registry,
                relationship_map,
                open_thread_map,
                block_summaries,
                event_timeline,
                alias_map,
                world_rules,
            )

        return {
            "story_memory": {
                "block_count": len(ordered_packets),
                "entity_registry": entity_registry,
                "alias_map": alias_map,
                "relationship_ledger": list(relationship_map.values()),
                "event_timeline": event_timeline,
                "open_threads": list(open_thread_map.values()),
                "world_rules": world_rules,
                "block_summaries": block_summaries,
            },
            "snapshots": snapshots,
        }

    def _snapshot(
        self,
        block_id: str,
        block_summaries: Sequence[Dict[str, Any]],
        entity_registry: Dict[str, Dict[str, Any]],
        relationship_map: Dict[Tuple[str, str], Dict[str, Any]],
        open_thread_map: Dict[str, Dict[str, Any]],
        alias_map: Dict[str, str],
        limits: Dict[str, int],
        block_map: Dict[str, Dict[str, Any]],
        anchors: Sequence[Dict[str, Any]],
        sketch_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        story_so_far = "\n".join(item["summary"] for item in block_summaries).strip()
        if len(story_so_far) > limits["summary"]:
            story_so_far = story_so_far[-limits["summary"]:]
        relevant_entities = sorted(
            entity_registry.values(),
            key=lambda item: (-len(item.get("mention_blocks", [])), item["name"]),
        )[:limits["entities"]]
        relevant_relationships = self._relationship_items(relationship_map)[-limits["relationships"]:]
        return {
            "block_id": block_id,
            "story_so_far": story_so_far,
            "recent_blocks": list(block_summaries[-RECENT_BLOCK_LIMIT:]),
            "relevant_entities": relevant_entities,
            "relevant_relationships": relevant_relationships,
            "open_threads": list(open_thread_map.values())[:limits["threads"]],
            "alias_map": dict(alias_map),
            "nearest_anchor": self._nearest_anchor(block_id, anchors),
            "block_fingerprints": self._block_fingerprints(block_id, block_map, sketch_map),
        }

    def _adaptive_limits(self, total_blocks: int) -> Dict[str, int]:
        if total_blocks <= 10:
            return {"summary": 2000, "entities": 12, "relationships": 12, "threads": 12}
        if total_blocks <= 30:
            return {"summary": 4000, "entities": 24, "relationships": 20, "threads": 16}
        if total_blocks <= 60:
            return {"summary": 6000, "entities": 40, "relationships": 30, "threads": 20}
        return {"summary": 8000, "entities": 60, "relationships": 40, "threads": 24}

    def _nearest_anchor(
        self,
        block_id: str,
        anchors: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        block_order = self._block_order(block_id)
        visible = [item for item in anchors if item.get("end_block_order", 0) < block_order]
        if not visible:
            return {}
        anchor = max(visible, key=lambda item: item.get("end_block_order", 0))
        return {"anchor_id": anchor.get("anchor_id"), "world_state": anchor.get("world_state", {})}

    def _block_fingerprints(
        self,
        block_id: str,
        block_map: Dict[str, Dict[str, Any]],
        sketch_map: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        block_order = self._block_order(block_id)
        previous_ids = sorted(
            [key for key in block_map if self._block_order(key) < block_order],
            key=self._block_order,
        )[-FINGERPRINT_BLOCK_LIMIT:]
        payload = []
        for previous_id in previous_ids:
            block = block_map[previous_id]
            fingerprints = [
                sketch_map[chapter_id].get("fingerprint", "")
                for chapter_id in block.get("owned_chapter_ids", [])
                if chapter_id in sketch_map and sketch_map[chapter_id].get("fingerprint")
            ]
            if fingerprints:
                payload.append({"block_id": previous_id, "fingerprints": fingerprints[:2]})
        return payload

    def _block_order(self, block_id: str) -> int:
        try:
            return int(block_id.rsplit("_", 1)[-1])
        except ValueError:
            return 0

    def _merge_packet(
        self,
        packet: Dict[str, Any],
        entity_registry: Dict[str, Dict[str, Any]],
        relationship_map: Dict[Tuple[str, str], Dict[str, Any]],
        open_thread_map: Dict[str, Dict[str, Any]],
        block_summaries: List[Dict[str, Any]],
        event_timeline: List[Dict[str, Any]],
        alias_map: Dict[str, str],
        world_rules: List[str],
    ) -> None:
        block_id = packet["block_id"]
        block_summaries.append({"block_id": block_id, "summary": packet.get("local_summary", "")})
        for entity in packet.get("local_entities", []):
            self._merge_entity(entity_registry, alias_map, block_id, entity)
        for event in packet.get("local_events", []):
            event_timeline.append({**event, "block_id": block_id})
        for change in packet.get("local_relationship_changes", []):
            self._merge_relationship(relationship_map, block_id, change)
        for thread in packet.get("local_threads", []):
            self._merge_thread(open_thread_map, block_id, thread)
        for rule in packet.get("world_rules", []):
            if rule and rule not in world_rules:
                world_rules.append(rule)

    def _merge_entity(
        self,
        entity_registry: Dict[str, Dict[str, Any]],
        alias_map: Dict[str, str],
        block_id: str,
        entity: Dict[str, Any],
    ) -> None:
        name = alias_map.get(entity["name"], entity["name"])
        record = entity_registry.setdefault(
            name,
            {
                "name": name,
                "entity_type": entity.get("entity_type", "character"),
                "aliases": [],
                "mention_blocks": [],
                "summary": entity.get("summary", ""),
                "evidence": [],
                "importance_tier": entity.get("importance_tier", "supporting"),
            },
        )
        if block_id not in record["mention_blocks"]:
            record["mention_blocks"].append(block_id)
        for alias in entity.get("aliases", []):
            if alias not in record["aliases"]:
                record["aliases"].append(alias)
            alias_map.setdefault(alias, name)
        for snippet in entity.get("evidence", [])[:2]:
            if snippet not in record["evidence"]:
                record["evidence"].append(snippet)
        if entity.get("summary"):
            record["summary"] = entity["summary"]

    def _merge_relationship(
        self,
        relationship_map: Dict[Tuple[str, str], Dict[str, Any]],
        block_id: str,
        change: Dict[str, Any],
    ) -> None:
        source, target = sorted((change.get("source", ""), change.get("target", "")))
        if not source or not target:
            return
        key = (source, target)
        record = relationship_map.setdefault(
            key,
            {"source": source, "target": target, "changes": []},
        )
        record["changes"].append(
            {
                "block_id": block_id,
                "change": change.get("change", "co_occurrence"),
                "weight": change.get("weight", 1),
                "evidence": change.get("evidence", [])[:3],
            }
        )

    def _merge_thread(
        self,
        open_thread_map: Dict[str, Dict[str, Any]],
        block_id: str,
        thread: Dict[str, Any],
    ) -> None:
        key = thread.get("thread_key", "")
        if not key:
            return
        payload = {
            "thread_key": key,
            "status": thread.get("status", "open"),
            "summary": thread.get("summary", ""),
            "chapter_id": thread.get("chapter_id"),
            "block_id": block_id,
        }
        if payload["status"] == "closed":
            open_thread_map.pop(key, None)
            return
        open_thread_map[key] = payload

    def _relationship_items(
        self,
        relationship_map: Dict[Tuple[str, str], Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        items = []
        for value in relationship_map.values():
            if not value["changes"]:
                continue
            items.append(
                {
                    "source": value["source"],
                    "target": value["target"],
                    "latest_change": value["changes"][-1],
                    "change_count": len(value["changes"]),
                }
            )
        items.sort(key=lambda item: item["latest_change"]["block_id"])
        return items
