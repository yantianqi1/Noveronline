"""基于故事记忆聚合兼容 seed_analysis 结构。"""

from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.reading_notes_manager import ReadingNotesManager


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
                    "summary": item.get("plot_summary", ""),
                }
            )
        return beats

    def _importance_tier(self, mentions: int) -> str:
        if mentions >= 4:
            return "protagonist"
        if mentions >= 2:
            return "major"
        return "supporting"

    # ------------------------------------------------------------------
    # New pipeline: ReadingNotesManager → aggregate_from_reading_notes
    # ------------------------------------------------------------------

    def aggregate_from_reading_notes(
        self,
        manager: "ReadingNotesManager",
        analysis_goal: str,
        project_name: str,
        agent_profiles: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Aggregate ReadingNotesManager data into a seed_analysis-compatible dict.

        Produces the same top-level keys as ``aggregate()`` plus enriched
        character/relation fields sourced from the new reading-notes format.
        """
        notes = manager.notes
        characters = self._characters_from_notes(notes["core_facts"]["characters"])
        organizations = self._organizations_from_notes(notes["core_facts"]["organizations"])
        relations = self._relations_from_graph(notes["relationship_graph"])
        chapter_beats = self._beats_from_summaries(manager.all_segment_summaries)

        return {
            "project_name": project_name,
            "analysis_goal": analysis_goal,
            "characters": characters,
            "organizations": organizations,
            "relations": relations,
            "chapter_beats": chapter_beats,
            "analysis_summary": (
                f"已从 {len(manager.all_segment_summaries)} 个段落聚合出 "
                f"{len(characters)} 名角色、{len(organizations)} 个组织、{len(relations)} 条关系。"
            ),
            "source_stats": {
                "block_count": len(manager.all_segment_summaries),
                "event_count": len(notes["relationship_graph"]),
                "character_count": len(characters),
                "organization_count": len(organizations),
                "relation_count": len(relations),
            },
            "story_memory": {
                "block_count": len(manager.all_segment_summaries),
                "entity_count": len(characters) + len(organizations),
                "open_thread_count": len(notes["plot_state"]["open_threads"]),
            },
        }

    def _characters_from_notes(self, characters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert ReadingNotesManager character dict to list format."""
        result = []
        for name, data in characters.items():
            mentions = len(data.get("segments_seen", []))
            result.append(
                {
                    "name": name,
                    "mention_count": mentions,
                    "importance_tier": self._importance_tier(mentions),
                    "identity_hint": data.get("identity", ""),
                    "profile_summary": " ".join(data.get("key_actions", [])[:3]),
                    "evidence": data.get("quote_examples", [])[:3],
                    # Enriched fields
                    "aliases": data.get("aliases", []),
                    "personality_traits": data.get("personality_traits", []),
                    "speech_style": data.get("speech_style", ""),
                    "status": data.get("status", ""),
                }
            )
        result.sort(key=lambda item: (-item["mention_count"], item["name"]))
        return result

    def _organizations_from_notes(self, organizations: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert ReadingNotesManager organization dict to list format."""
        result = []
        for name, data in organizations.items():
            mentions = len(data.get("segments_seen", []))
            result.append(
                {
                    "name": name,
                    "mention_count": mentions,
                    "importance_tier": "major" if mentions >= 2 else "supporting",
                    "organization_type": data.get("type", "organization"),
                    "summary": data.get("purpose", ""),
                    "evidence": [],
                }
            )
        result.sort(key=lambda item: (-item["mention_count"], item["name"]))
        return result

    def _relations_from_graph(self, graph: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Group relationship graph events by source|target pair."""
        pairs: Dict[str, Dict[str, Any]] = {}
        for entry in graph:
            source = entry.get("source", "")
            target = entry.get("target", "")
            key = f"{source}|{target}"
            if key not in pairs:
                pairs[key] = {
                    "source": source,
                    "target": target,
                    "relation_type": entry.get("relation", "co_occurrence"),
                    "weight": 0,
                    "evidence": [],
                    "evolution_chain": [],
                }
            rec = pairs[key]
            rec["weight"] += 1
            rec["relation_type"] = entry.get("relation", rec["relation_type"])
            ev = entry.get("evidence", "")
            if ev and ev not in rec["evidence"]:
                rec["evidence"].append(ev)
            rec["evolution_chain"].append(
                {
                    "state": entry.get("relation", ""),
                    "trigger": entry.get("trigger", ""),
                    "segment": entry.get("segment_id", ""),
                }
            )
        relations = list(pairs.values())
        for rel in relations:
            rel["evidence"] = rel["evidence"][:3]
        relations.sort(key=lambda item: (-item["weight"], item["source"], item["target"]))
        return relations

    def _beats_from_summaries(self, summaries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert segment summaries to chapter beats format (max 20)."""
        beats = []
        for index, entry in enumerate(summaries[:20], start=1):
            beats.append(
                {
                    "beat_id": f"beat_{index}",
                    "title": f"段落 {entry.get('segment_id', index)}",
                    "summary": entry.get("summary", ""),
                }
            )
        return beats
