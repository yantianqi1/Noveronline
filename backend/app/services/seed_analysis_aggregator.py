"""基于故事记忆聚合兼容 seed_analysis 结构。"""

from typing import Any, Dict, List, Optional, Sequence, TYPE_CHECKING

from ..config import Settings

if TYPE_CHECKING:
    from app.services.reading_notes_manager import ReadingNotesManager


def _evidence_cap() -> int:
    return Settings().SEED_MAX_EVIDENCE_PER_ITEM


def _chapter_beats_cap() -> int:
    return Settings().SEED_MAX_CHAPTER_BEATS


def _mention_min_protagonist() -> int:
    return Settings().SEED_MENTION_MIN_PROTAGONIST


def _mention_min_major() -> int:
    return Settings().SEED_MENTION_MIN_MAJOR


def _org_mention_min_major() -> int:
    return Settings().SEED_ORG_MENTION_MIN_MAJOR


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
                    "evidence": item.get("evidence", [])[: _evidence_cap()],
                }
            )
        result.sort(key=lambda item: (-item["mention_count"], item["name"]))
        return result

    def _organizations(self, entities: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = []
        org_min_major = _org_mention_min_major()
        for item in entities:
            if item.get("entity_type") != "organization":
                continue
            mentions = len(item.get("mention_blocks", []))
            result.append(
                {
                    "name": item["name"],
                    "mention_count": mentions,
                    "importance_tier": "major" if mentions >= org_min_major else "supporting",
                    "organization_type": item.get("organization_type", "organization"),
                    "summary": item.get("summary", ""),
                    "evidence": item.get("evidence", [])[: _evidence_cap()],
                }
            )
        result.sort(key=lambda item: (-item["mention_count"], item["name"]))
        return result

    def _relations(self, ledger: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        relations = []
        evidence_cap = _evidence_cap()
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
                    "evidence": evidence[:evidence_cap],
                }
            )
        relations.sort(key=lambda item: (-item["weight"], item["source"], item["target"]))
        return relations

    def _chapter_beats(self, block_analyses: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        beats = []
        cap = _chapter_beats_cap()
        for index, item in enumerate(block_analyses[:cap], start=1):
            beats.append(
                {
                    "beat_id": f"beat_{index}",
                    "title": f"剧情块 {index}",
                    "summary": item.get("plot_summary", ""),
                }
            )
        return beats

    def _importance_tier(self, mentions: int) -> str:
        if mentions >= _mention_min_protagonist():
            return "protagonist"
        if mentions >= _mention_min_major():
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
        completed_summaries = [
            s for s in manager.all_segment_summaries
            if s.get("status") != "retry_needed"
        ]
        chapter_beats = self._beats_from_summaries(completed_summaries)
        volume_themes = self._volume_themes_from_notes(
            notes["plot_state"].get("volume_summaries", [])
        )

        completed_count = len(completed_summaries)
        total_count = len(manager.all_segment_summaries)
        analysis_summary = (
            f"已从 {completed_count} 个段落聚合出 "
            f"{len(characters)} 名角色、{len(organizations)} 个组织、{len(relations)} 条关系。"
        )
        if total_count > completed_count:
            analysis_summary += f" ({total_count - completed_count} 个段落等待手动重读)"
        if volume_themes:
            theme_lines = [
                f"[{t['volume_id']}] {t['theme']}"
                for t in volume_themes if t.get("theme")
            ]
            if theme_lines:
                analysis_summary += " 卷主题：" + " / ".join(theme_lines)

        return {
            "project_name": project_name,
            "analysis_goal": analysis_goal,
            "characters": characters,
            "organizations": organizations,
            "relations": relations,
            "chapter_beats": chapter_beats,
            "analysis_summary": analysis_summary,
            "source_stats": {
                "block_count": completed_count,
                "event_count": len(notes["relationship_graph"]),
                "character_count": len(characters),
                "organization_count": len(organizations),
                "relation_count": len(relations),
            },
            "story_memory": {
                "block_count": completed_count,
                "entity_count": len(characters) + len(organizations),
                "open_thread_count": len(notes["plot_state"]["open_threads"]),
            },
            "volume_themes": volume_themes,
        }

    def _volume_themes_from_notes(
        self, volume_summaries: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract structured volume metadata for downstream consumers (UI / ontology).

        Only volumes whose ``status`` is not ``retry_needed`` are surfaced. Empty
        list when the new structured fields are absent (back-compat with old
        reading_notes.json files that pre-date the Phase D extension).
        """
        out: List[Dict[str, Any]] = []
        for vol in volume_summaries:
            if vol.get("status") == "retry_needed":
                continue
            theme = (vol.get("theme") or "").strip()
            main_arcs = vol.get("main_arcs") or []
            faction_changes = vol.get("faction_changes") or []
            cross_threads = vol.get("cross_volume_threads") or []
            if not (theme or main_arcs or faction_changes or cross_threads):
                continue
            out.append(
                {
                    "volume_id": vol.get("volume_id", ""),
                    "theme": theme,
                    "main_arcs": list(main_arcs),
                    "faction_changes": list(faction_changes),
                    "cross_volume_threads": list(cross_threads),
                }
            )
        return out

    def _characters_from_notes(self, characters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Convert ReadingNotesManager character dict to list format."""
        result = []
        evidence_cap = _evidence_cap()
        for name, data in characters.items():
            mentions = len(data.get("segments_seen", []))
            result.append(
                {
                    "name": name,
                    "mention_count": mentions,
                    "importance_tier": self._importance_tier(mentions),
                    "identity_hint": data.get("identity", ""),
                    "profile_summary": " ".join(data.get("key_actions", [])[:3]),
                    "evidence": data.get("quote_examples", [])[:evidence_cap],
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
        org_min_major = _org_mention_min_major()
        for name, data in organizations.items():
            mentions = len(data.get("segments_seen", []))
            result.append(
                {
                    "name": name,
                    "mention_count": mentions,
                    "importance_tier": "major" if mentions >= org_min_major else "supporting",
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
        evidence_cap = _evidence_cap()
        for rel in relations:
            rel["evidence"] = rel["evidence"][:evidence_cap]
        relations.sort(key=lambda item: (-item["weight"], item["source"], item["target"]))
        return relations

    def _beats_from_summaries(self, summaries: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert segment summaries to chapter beats format.

        Skips any entry marked ``status=retry_needed`` so upstream callers
        that forget to pre-filter still don't leak placeholders into the
        chapter beats. Cap is governed by ``SEED_MAX_CHAPTER_BEATS`` so long
        novels can keep their full timeline.
        """
        beats = []
        index = 0
        cap = _chapter_beats_cap()
        for entry in summaries:
            if entry.get("status") == "retry_needed":
                continue
            if index >= cap:
                break
            index += 1
            beats.append(
                {
                    "beat_id": f"beat_{index}",
                    "title": f"段落 {entry.get('segment_id', index)}",
                    "summary": entry.get("summary", ""),
                }
            )
        return beats
