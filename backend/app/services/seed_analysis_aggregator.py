"""基于故事记忆聚合兼容 seed_analysis 结构。"""

from typing import Any, Dict, List, Sequence


class SeedAnalysisAggregator:
    """把故事记忆与块分析汇总成旧接口兼容的种子分析。"""

    def aggregate(
        self,
        story_memory: Dict[str, Any],
        block_analyses: Sequence[Dict[str, Any]],
        analysis_goal: str,
        project_name: str,
    ) -> Dict[str, Any]:
        entities = list(story_memory.get("entity_registry", {}).values())
        characters = self._characters(entities)
        organizations = self._organizations(entities)
        relations = self._relations(story_memory.get("relationship_ledger", []))
        chapter_beats = self._chapter_beats(block_analyses)
        return {
            "project_name": project_name,
            "analysis_goal": analysis_goal,
            "characters": characters,
            "organizations": organizations,
            "relations": relations,
            "chapter_beats": chapter_beats,
            "analysis_summary": (
                f"已从 {story_memory.get('block_count', 0)} 个剧情块聚合出 "
                f"{len(characters)} 名角色、{len(organizations)} 个组织、{len(relations)} 条关系。"
            ),
            "source_stats": {
                "block_count": story_memory.get("block_count", 0),
                "event_count": len(story_memory.get("event_timeline", [])),
                "character_count": len(characters),
                "organization_count": len(organizations),
                "relation_count": len(relations),
            },
            "story_memory": {
                "block_count": story_memory.get("block_count", 0),
                "entity_count": len(entities),
                "open_thread_count": len(story_memory.get("open_threads", [])),
            },
        }

    def _characters(self, entities: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for item in entities:
            if item.get("entity_type") != "character":
                continue
            mentions = len(item.get("mention_blocks", []))
            result.append(
                {
                    "name": item["name"],
                    "mention_count": mentions,
                    "importance_tier": self._importance_tier(mentions),
                    "identity_hint": "关键角色",
                    "profile_summary": item.get("summary", ""),
                    "evidence": item.get("evidence", [])[:3],
                }
            )
        result.sort(key=lambda item: (-item["mention_count"], item["name"]))
        return result

    def _organizations(self, entities: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        for item in entities:
            if item.get("entity_type") != "organization":
                continue
            mentions = len(item.get("mention_blocks", []))
            result.append(
                {
                    "name": item["name"],
                    "mention_count": mentions,
                    "importance_tier": "major" if mentions >= 2 else "supporting",
                    "organization_type": item.get("organization_type", "organization"),
                    "summary": item.get("summary", ""),
                    "evidence": item.get("evidence", [])[:3],
                }
            )
        result.sort(key=lambda item: (-item["mention_count"], item["name"]))
        return result

    def _relations(self, ledger: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        relations = []
        for item in ledger:
            changes = item.get("changes", [])
            if not changes:
                continue
            latest = changes[-1]
            evidence = []
            for change in changes:
                evidence.extend(change.get("evidence", [])[:1])
            relations.append(
                {
                    "source": item.get("source", ""),
                    "target": item.get("target", ""),
                    "relation_type": latest.get("change", "co_occurrence"),
                    "weight": len(changes),
                    "evidence": evidence[:3],
                }
            )
        relations.sort(key=lambda item: (-item["weight"], item["source"], item["target"]))
        return relations

    def _chapter_beats(self, block_analyses: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        beats = []
        for index, item in enumerate(block_analyses[:8], start=1):
            beats.append(
                {
                    "beat_id": f"beat_{index}",
                    "title": f"剧情块 {index}",
                    "summary": item.get("plot_summary", "")[:120],
                }
            )
        return beats

    def _importance_tier(self, mentions: int) -> str:
        if mentions >= 4:
            return "protagonist"
        if mentions >= 2:
            return "major"
        return "supporting"
