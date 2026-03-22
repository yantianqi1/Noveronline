"""连续性一致性审计服务。"""

from typing import Any, Dict, List, Sequence


REVIVAL_HINTS = ("复活", "回魂", "苏醒", "死而复生", "重生")


class ContinuityConsistencyAuditor:
    """显式暴露跨块矛盾与歧义。"""

    def audit(
        self,
        story_memory: Dict[str, Any],
        block_analyses: Sequence[Dict[str, Any]],
        local_block_facts: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        conflicts = self._post_death_conflicts(block_analyses)
        ambiguities = self._alias_ambiguities(local_block_facts)
        return {
            "conflict_count": len(conflicts),
            "ambiguity_count": len(ambiguities),
            "conflicts": conflicts,
            "ambiguities": ambiguities,
            "summary": self._summary(story_memory, conflicts, ambiguities),
        }

    def _post_death_conflicts(self, block_analyses: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        first_death = {}
        conflicts = []
        for analysis in sorted(block_analyses, key=lambda item: item["block_id"]):
            for update in analysis.get("character_state_updates", []):
                name = update.get("name", "")
                state = update.get("state", "")
                evidence = " ".join(update.get("evidence", []))
                if state == "dead" and name not in first_death:
                    first_death[name] = analysis["block_id"]
                    continue
                if name in first_death and state != "dead" and not self._looks_like_revival(evidence):
                    conflicts.append(
                        {
                            "kind": "post_death_activity",
                            "name": name,
                            "death_block_id": first_death[name],
                            "activity_block_id": analysis["block_id"],
                            "evidence": update.get("evidence", [])[:2],
                        }
                    )
        return conflicts

    def _alias_ambiguities(self, local_block_facts: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ambiguities = []
        for packet in local_block_facts:
            for item in packet.get("unresolved_refs", []):
                candidates = item.get("candidate_names", [])
                if len(candidates) < 2:
                    continue
                ambiguities.append(
                    {
                        "block_id": packet.get("block_id", ""),
                        "alias": item.get("alias", ""),
                        "candidate_names": candidates,
                        "reason": item.get("reason", "存在多个候选实体"),
                    }
                )
        return ambiguities

    def _looks_like_revival(self, evidence: str) -> bool:
        return any(hint in evidence for hint in REVIVAL_HINTS)

    def _summary(
        self,
        story_memory: Dict[str, Any],
        conflicts: Sequence[Dict[str, Any]],
        ambiguities: Sequence[Dict[str, Any]],
    ) -> str:
        return (
            f"已审计 {story_memory.get('block_count', 0)} 个剧情块，"
            f"发现 {len(conflicts)} 条显式冲突，"
            f"{len(ambiguities)} 条别名歧义。"
        )
