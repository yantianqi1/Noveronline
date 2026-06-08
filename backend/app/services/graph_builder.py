"""本地图谱构建服务。"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..database import get_engine
from ..models.project import ProjectManager  # noqa: F401 — re-exported for historical test patches
from ..models.task import TaskManager
from ..repositories.graph_repo import GraphRepository
from .graph_builder_types import GraphInfo
from .graph_builder_worker import run_graph_build
from .local_story_graph_builder import LocalStoryGraphBuilder


class GraphBuilderService:
    def __init__(
        self,
        builder: Optional[LocalStoryGraphBuilder] = None,
        repo: Optional[GraphRepository] = None,
    ):
        self.builder = builder or LocalStoryGraphBuilder()
        self._repo = repo or GraphRepository(get_engine())
        self.task_manager = TaskManager()

    async def build_graph_async(
        self,
        project_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str = "Novel Story Graph",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> str:
        task_id = await self.task_manager.create_task(
            task_type="graph_build",
            metadata={
                "project_id": project_id,
                "graph_name": graph_name,
                "chunk_size": chunk_size,
                "text_length": len(text),
            },
        )
        asyncio.create_task(
            self._build_graph_worker(task_id, project_id, text, ontology, graph_name, chunk_size, chunk_overlap)
        )
        return task_id

    async def _build_graph_worker(
        self,
        task_id: str,
        project_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        chunk_size: int,
        chunk_overlap: int,
    ) -> None:
        self.task_manager._ensure_loop()
        await asyncio.to_thread(
            run_graph_build, self, task_id, project_id, text, ontology, graph_name, chunk_size, chunk_overlap,
        )

    def build_graph(
        self,
        project_id: str,
        text: str,
        ontology: Dict[str, Any],
        graph_name: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        structured_inputs = self._structured_inputs_for_graph(project_id)
        if structured_inputs:
            story_memory, local_block_facts, block_analyses, chapter_continuity = structured_inputs
        else:
            local_block_facts = self._optional_json(project_id, "local_block_facts.json")
            block_analyses = self._optional_json(project_id, "block_analyses.json")
            chapter_continuity = self._optional_json(project_id, "chapter_continuity.json")
            reading_notes = self._optional_json(project_id, "reading_notes.json")
            seed_analysis = self._optional_json(project_id, "seed_analysis.json")
            if (
                not all([local_block_facts, block_analyses, chapter_continuity])
                and reading_notes is not None
                and seed_analysis is not None
            ):
                from .reading_notes_graph_adapter import adapt_reading_notes_for_graph

                smart_segments = self._optional_json(project_id, "smart_segments.json")
                chapter_segs = self._optional_json(project_id, "chapter_segments.json")
                story_memory, local_block_facts, block_analyses, chapter_continuity = (
                    adapt_reading_notes_for_graph(reading_notes, seed_analysis, smart_segments, chapter_segs)
                )
            else:
                story_memory = self._optional_json(project_id, "story_memory.json")
                if not all([local_block_facts, block_analyses, story_memory, chapter_continuity]):
                    from .reading_notes_graph_adapter import adapt_reading_notes_for_graph

                    reading_notes = (
                        reading_notes
                        if reading_notes is not None
                        else self._required_json(project_id, "reading_notes.json")
                    )
                    seed_analysis = (
                        seed_analysis
                        if seed_analysis is not None
                        else self._required_json(project_id, "seed_analysis.json")
                    )
                    smart_segments = self._optional_json(project_id, "smart_segments.json")
                    chapter_segs = self._optional_json(project_id, "chapter_segments.json")
                    story_memory, local_block_facts, block_analyses, chapter_continuity = (
                        adapt_reading_notes_for_graph(reading_notes, seed_analysis, smart_segments, chapter_segs)
                    )

        return self.builder.build_for_project(
            project_id=project_id,
            graph_name=graph_name,
            ontology=ontology,
            extracted_text=text,
            local_block_facts=local_block_facts,
            block_analyses=block_analyses,
            story_memory=story_memory,
            chapter_continuity=chapter_continuity,
            progress_callback=progress_callback,
        )

    def get_graph_data(self, graph_id: str) -> Dict[str, Any]:
        from .local_story_graph_support import project_id_from_graph_id
        project_id = project_id_from_graph_id(graph_id)
        meta = self._repo.load_snapshot(project_id) or {}
        nodes = self._repo.load_all_nodes(project_id)
        edges = self._repo.load_all_edges(project_id)
        return {
            "graph_id": meta.get("graph_id", graph_id),
            "project_id": meta.get("project_id", project_id),
            "graph_name": meta.get("graph_name", ""),
            "built_at": meta.get("built_at", ""),
            "build_version": meta.get("build_version", ""),
            "nodes": nodes,
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
        }

    def get_graph_info(self, graph_id: str) -> GraphInfo:
        payload = self.get_graph_data(graph_id)
        entity_types = sorted({
            label
            for node in payload.get("nodes", [])
            for label in node.get("labels", [])
            if label not in {"Entity", "Node"}
        })
        return GraphInfo(
            graph_id=payload["graph_id"],
            node_count=payload.get("node_count", len(payload.get("nodes", []))),
            edge_count=payload.get("edge_count", len(payload.get("edges", []))),
            entity_types=entity_types,
        )

    def _required_json(self, project_id: str, filename: str) -> Dict[str, Any]:
        from ..repositories.project_artifact_repo import load_project_artifact

        payload = load_project_artifact(project_id, filename)
        if payload is None:
            raise ValueError(f"项目缺少构建本地图谱所需工件: {filename}")
        return payload

    def _optional_json(self, project_id: str, filename: str) -> Optional[Dict[str, Any]]:
        from ..repositories.project_artifact_repo import load_project_artifact

        return load_project_artifact(project_id, filename)

    def _structured_inputs_for_graph(
        self, project_id: str
    ) -> Optional[Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]]:
        from ..repositories.entity_repo import EntityRepository
        from ..repositories.event_repo import EventRepository
        from ..repositories.relationship_repo import RelationshipRepository
        from ..repositories.thread_repo import ThreadRepository
        from ..repositories.world_rule_repo import WorldRuleRepository
        from .chapter_meta_service import ChapterMetaService

        engine = get_engine()
        entity_repo = EntityRepository(engine)
        entities = [
            entity_repo.get_entity_with_details(project_id, row["entity_id"]) or row
            for row in entity_repo.list_entities(project_id, limit=1000)
        ]
        relationships = RelationshipRepository(engine).list_relationships(project_id, limit=1000)
        event_repo = EventRepository(engine)
        events = event_repo.list_character_events(project_id, limit=1000)
        relationship_events = event_repo.list_relationship_events(project_id, limit=1000)
        world_rules = WorldRuleRepository(engine).list_rules(project_id, limit=1000)
        open_threads = ThreadRepository(engine).get_open_threads(project_id)
        chapters = ChapterMetaService().get_chapter_summaries(project_id)
        evidence_by_entity = self._graph_entity_evidence_from_db(project_id)
        if not any([
            entities,
            relationships,
            events,
            relationship_events,
            world_rules,
            open_threads,
            chapters,
        ]):
            return None

        id_to_name = {item["entity_id"]: item["name"] for item in entities if item.get("entity_id") and item.get("name")}
        event_timeline = self._graph_event_timeline_from_db(events, id_to_name)
        event_timeline.extend(
            self._graph_relationship_event_timeline_from_db(relationship_events, id_to_name)
        )
        relationship_ledger = self._graph_relationship_ledger_from_db(relationships, id_to_name)
        relationship_ledger.extend(
            self._graph_relationship_event_ledger_from_db(relationship_events, id_to_name)
        )
        story_memory = {
            "block_count": max(len(chapters), 1),
            "entity_registry": self._graph_entity_registry_from_db(entities),
            "alias_map": self._graph_alias_map_from_db(entities),
            "relationship_ledger": relationship_ledger,
            "event_timeline": event_timeline,
            "open_threads": self._merge_graph_open_threads(
                self._graph_open_threads_from_db(open_threads),
                self._graph_open_threads_from_chapters(chapters),
            ),
            "world_rules": [
                str(item.get("fact_text") or "").strip()
                for item in world_rules
                if str(item.get("fact_text") or "").strip()
            ],
            "block_summaries": [],
        }
        evidence_packets = self._graph_local_evidence_packets_from_db(entities, evidence_by_entity)
        local_block_facts = {"block_count": story_memory["block_count"], "packets": evidence_packets}
        block_analyses = {"block_count": story_memory["block_count"]}
        chapter_continuity = {
            "chapter_count": len(chapters),
            "chapters": [
                {
                    "chapter_id": chapter["chapter_id"],
                    "order": chapter["chapter_order"],
                    "title": chapter.get("title", ""),
                    "continuity_summary": chapter.get("summary_text", ""),
                }
                for chapter in chapters
            ],
        }
        return story_memory, local_block_facts, block_analyses, chapter_continuity

    def _graph_entity_evidence_from_db(self, project_id: str) -> Dict[str, List[Dict[str, Any]]]:
        from sqlalchemy import select

        from ..tables.novel import entity_evidence

        stmt = (
            select(entity_evidence)
            .where(
                (entity_evidence.c.project_id == project_id)
                & (entity_evidence.c.owner_type == "entity")
            )
            .order_by(entity_evidence.c.created_at.desc())
            .limit(1000)
        )
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        with get_engine().connect() as conn:
            for row in conn.execute(stmt).fetchall():
                item = dict(row._mapping)
                owner_id = str(item.get("owner_id") or "")
                snippet = str(item.get("snippet") or "").strip()
                if not owner_id or not snippet:
                    continue
                grouped.setdefault(owner_id, []).append(item)
        return grouped

    def _graph_local_evidence_packets_from_db(
        self,
        entities: List[Dict[str, Any]],
        evidence_by_entity: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, Any]]:
        packets = []
        id_to_name = {
            str(entity.get("entity_id") or ""): str(entity.get("name") or "").strip()
            for entity in entities
            if entity.get("entity_id") and str(entity.get("name") or "").strip()
        }
        for entity_id, evidence_rows in evidence_by_entity.items():
            name = id_to_name.get(entity_id, "")
            if not name:
                continue
            for row in evidence_rows[:5]:
                snippet = str(row.get("snippet") or "").strip()
                if not snippet:
                    continue
                packets.append(
                    {
                        "block_id": row.get("evidence_id", ""),
                        "owned_chapters": [row.get("chapter_id", "")],
                        "local_entities": [
                            {
                                "name": name,
                                "evidence": [snippet],
                            }
                        ],
                    }
                )
        return packets

    def _graph_entity_registry_from_db(self, entities: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        registry = {}
        for entity in entities:
            name = str(entity.get("name") or "").strip()
            if not name:
                continue
            aliases = [
                alias
                for alias in entity.get("aliases", [])
                if alias and alias != name
            ]
            registry[name] = {
                "entity_type": str(entity.get("entity_type") or "character").lower(),
                "summary": entity.get("summary") or name,
                "importance_tier": entity.get("importance_tier") or "supporting",
                "aliases": aliases,
                "mention_blocks": [],
                "evidence": [entity.get("summary") or name],
            }
        return registry

    def _graph_alias_map_from_db(self, entities: List[Dict[str, Any]]) -> Dict[str, str]:
        alias_map = {}
        for entity in entities:
            name = str(entity.get("name") or "").strip()
            if not name:
                continue
            for alias in entity.get("aliases", []):
                alias = str(alias or "").strip()
                if alias and alias != name:
                    alias_map[alias] = name
        return alias_map

    def _graph_relationship_ledger_from_db(
        self, relationships: List[Dict[str, Any]], id_to_name: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        ledger = []
        for relationship in relationships:
            source = id_to_name.get(relationship.get("source_id", ""))
            target = id_to_name.get(relationship.get("target_id", ""))
            if not source or not target:
                continue
            description = str(relationship.get("description") or relationship.get("history") or "").strip()
            ledger.append(
                {
                    "source": source,
                    "target": target,
                    "changes": [
                        {
                            "change": str(relationship.get("relation_type") or "related").lower(),
                            "chapter_id": "",
                            "block_id": relationship.get("relation_id", ""),
                            "evidence": [description] if description else [],
                        }
                    ],
                }
            )
        return ledger

    def _graph_relationship_event_ledger_from_db(
        self, relationship_events: List[Dict[str, Any]], id_to_name: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for event in sorted(
            relationship_events,
            key=lambda item: (
                int(item.get("chapter_order") or 0),
                str(item.get("created_at") or ""),
                str(item.get("event_id") or ""),
            ),
        ):
            source = id_to_name.get(event.get("source_entity_id", ""))
            target = id_to_name.get(event.get("target_entity_id", ""))
            if not source or not target:
                continue
            change = str(event.get("relation_type") or event.get("new_state") or "related").strip()
            evidence = self._relationship_event_evidence(event)
            key = (source, target)
            item = grouped.setdefault(key, {"source": source, "target": target, "changes": []})
            item["changes"].append(
                {
                    "change": change.lower() if change else "related",
                    "chapter_id": self._chapter_id_from_order(event.get("chapter_order")),
                    "block_id": event.get("segment_id") or event.get("event_id", ""),
                    "evidence": evidence,
                }
            )
        return list(grouped.values())

    def _graph_event_timeline_from_db(
        self, events: List[Dict[str, Any]], id_to_name: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        timeline = []
        for event in events:
            actor = id_to_name.get(event.get("entity_id", ""))
            summary = str(event.get("summary") or "").strip()
            if not actor or not summary:
                continue
            chapter_order = int(event.get("chapter_order") or 0)
            timeline.append(
                {
                    "event_id": event.get("event_id", ""),
                    "title": summary,
                    "summary": summary,
                    "kind": event.get("event_type", ""),
                    "chapter_id": f"chapter_{chapter_order:04d}" if chapter_order else "",
                    "block_id": event.get("segment_id", ""),
                    "characters": [actor],
                    "organizations": [],
                    "evidence": [summary],
                }
            )
        return timeline

    def _graph_relationship_event_timeline_from_db(
        self, relationship_events: List[Dict[str, Any]], id_to_name: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        timeline = []
        for event in relationship_events:
            source = id_to_name.get(event.get("source_entity_id", ""))
            target = id_to_name.get(event.get("target_entity_id", ""))
            if not source or not target:
                continue
            summary = self._relationship_event_summary(event, source, target)
            if not summary:
                continue
            chapter_order = int(event.get("chapter_order") or 0)
            timeline.append(
                {
                    "event_id": event.get("event_id", ""),
                    "title": str(event.get("trigger_event") or "").strip() or summary,
                    "summary": summary,
                    "kind": f"relationship:{event.get('relation_type') or event.get('new_state') or 'change'}",
                    "chapter_id": self._chapter_id_from_order(chapter_order),
                    "block_id": event.get("segment_id", ""),
                    "characters": [source, target],
                    "organizations": [],
                    "evidence": self._relationship_event_evidence(event) or [summary],
                }
            )
        return timeline

    def _relationship_event_summary(
        self, event: Dict[str, Any], source: str, target: str
    ) -> str:
        for key in ("trigger_event", "evidence", "emotional_shift", "power_shift"):
            value = str(event.get(key) or "").strip()
            if value:
                return value
        state = str(event.get("new_state") or event.get("relation_type") or "").strip()
        return f"{source}与{target}关系变化为{state}" if state else ""

    def _relationship_event_evidence(self, event: Dict[str, Any]) -> List[str]:
        values = []
        for key in ("evidence", "trigger_event", "emotional_shift", "power_shift"):
            value = str(event.get(key) or "").strip()
            if value and value not in values:
                values.append(value)
        return values

    def _chapter_id_from_order(self, chapter_order: Any) -> str:
        order = int(chapter_order or 0)
        return f"chapter_{order:04d}" if order else ""

    def _graph_open_threads_from_db(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        threads = []
        for row in rows:
            thread_key = str(row.get("thread_key") or "").strip()
            detail = str(row.get("detail") or "").strip()
            summary = detail or thread_key
            if not thread_key and not summary:
                continue
            item = {
                "thread_id": str(row.get("thread_id") or "").strip(),
                "thread_key": thread_key or summary,
                "summary": summary,
                "status": str(row.get("status") or "open").strip() or "open",
            }
            source_chapter = str(row.get("source_chapter") or "").strip()
            if source_chapter:
                item["source_chapter"] = source_chapter
            threads.append(item)
        return threads

    def _graph_open_threads_from_chapters(self, chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        threads = []
        seen = set()
        for chapter in chapters:
            for raw_thread in chapter.get("open_threads", []):
                if isinstance(raw_thread, dict):
                    thread_key = str(raw_thread.get("thread_key") or raw_thread.get("summary") or "").strip()
                    summary = str(raw_thread.get("summary") or thread_key).strip()
                    status = str(raw_thread.get("status") or "open").strip() or "open"
                else:
                    summary = str(raw_thread).strip()
                    thread_key = summary
                    status = "open"
                if not thread_key or thread_key in seen:
                    continue
                seen.add(thread_key)
                threads.append({"thread_key": thread_key, "summary": summary, "status": status})
        return threads

    def _merge_graph_open_threads(
        self, *groups: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        merged = []
        seen = set()
        for group in groups:
            for thread in group:
                thread_key = str(thread.get("thread_key") or thread.get("summary") or "").strip()
                if not thread_key or thread_key in seen:
                    continue
                seen.add(thread_key)
                merged.append(thread)
        return merged
