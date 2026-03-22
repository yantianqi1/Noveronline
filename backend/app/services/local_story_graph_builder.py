"""本地图谱构建器。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .local_story_graph_models import EvidenceRef, GraphEdge, GraphNode, GraphSnapshot
from .local_story_graph_storage import LocalStoryGraphStorage
from .local_story_graph_support import (
    DEFAULT_ARTIFACT_EDGE,
    DEFAULT_EVENT_EDGE,
    DEFAULT_LOCATION_EDGE,
    DEFAULT_RELATIONSHIP_EDGE,
    DEFAULT_RULE_EDGE,
    cooccurring_names,
    dedupe_evidence,
    edge_uuid,
    evidence_ref,
    find_artifact_candidates,
    labels_for_entity,
    local_graph_id,
    node_uuid,
    normalize_name,
    preferred_edge_name,
    preferred_entity_label,
    split_sentences,
    stable_hash,
    unique_strings,
)


class LocalStoryGraphBuilder:
    def __init__(self, storage: Optional[LocalStoryGraphStorage] = None):
        self.storage = storage or LocalStoryGraphStorage()

    def build_for_project(
        self,
        project_id: str,
        graph_name: str,
        ontology: Dict[str, Any],
        extracted_text: str,
        local_block_facts: Dict[str, Any],
        block_analyses: Dict[str, Any],
        story_memory: Dict[str, Any],
        chapter_continuity: Dict[str, Any],
    ) -> GraphSnapshot:
        nodes = self._build_nodes(project_id, ontology, extracted_text, local_block_facts, story_memory)
        edges = self._build_edges(project_id, ontology, nodes, extracted_text, local_block_facts, story_memory)
        built_at = datetime.now().isoformat()
        snapshot = GraphSnapshot(
            graph_id=local_graph_id(project_id),
            project_id=project_id,
            graph_name=graph_name,
            built_at=built_at,
            build_version=stable_hash(project_id, built_at, str(len(nodes)), str(len(edges))),
            ontology={
                **ontology,
                "source_artifacts": {
                    "local_block_facts": local_block_facts.get("block_count", 0),
                    "block_analyses": block_analyses.get("block_count", 0),
                    "story_memory_entities": len(story_memory.get("entity_registry", {})),
                    "chapter_continuity": chapter_continuity.get("chapter_count", 0),
                },
            },
            nodes=nodes,
            edges=edges,
        )
        self.storage.save_snapshot(project_id, snapshot)
        return snapshot

    def _build_nodes(
        self,
        project_id: str,
        ontology: Dict[str, Any],
        extracted_text: str,
        local_block_facts: Dict[str, Any],
        story_memory: Dict[str, Any],
    ) -> List[GraphNode]:
        candidates = []
        packets = list(local_block_facts.get("packets", []))
        registry = story_memory.get("entity_registry", {})
        for name, item in registry.items():
            candidates.extend(self._registry_candidates(ontology, name, item, packets))
        for event in story_memory.get("event_timeline", []):
            candidates.append(self._event_candidate(ontology, event))
        for rule_text in story_memory.get("world_rules", []):
            candidates.append(self._rule_candidate(ontology, rule_text))
        candidates.extend(self._raw_candidates(ontology, extracted_text, registry))
        return self._merge_node_candidates(project_id, candidates)

    def _build_edges(
        self,
        project_id: str,
        ontology: Dict[str, Any],
        nodes: List[GraphNode],
        extracted_text: str,
        local_block_facts: Dict[str, Any],
        story_memory: Dict[str, Any],
    ) -> List[GraphEdge]:
        lookup = self._node_lookup(nodes)
        candidates = []
        candidates.extend(self._relationship_edges(ontology, story_memory, lookup))
        candidates.extend(self._event_edges(ontology, story_memory, lookup))
        candidates.extend(self._artifact_edges(ontology, extracted_text, lookup))
        candidates.extend(self._rule_edges(ontology, story_memory, lookup))
        return self._merge_edge_candidates(project_id, candidates)

    def _registry_candidates(self, ontology: Dict[str, Any], name: str, item: Dict[str, Any], packets: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        entity_type = str(item.get("entity_type") or "character")
        label = preferred_entity_label(ontology, entity_type.capitalize(), fallback=entity_type.capitalize())
        evidence = self._entity_evidence(name, packets, item.get("evidence", []))
        candidates = [{
            "name": name,
            "label": label,
            "summary": item.get("summary", "") or name,
            "attributes": {
                "importance_tier": item.get("importance_tier", "supporting"),
                "organization_type": item.get("organization_type", "organization"),
                "aliases": unique_strings(item.get("aliases", [])),
                "mention_blocks": list(item.get("mention_blocks", [])),
            },
            "evidence_refs": evidence,
        }]
        if self._should_add_faction(item, name, ontology):
            candidates.append({**candidates[0], "label": preferred_entity_label(ontology, "Faction", fallback="Faction")})
        return candidates

    def _event_candidate(self, ontology: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
        snippets = [evidence_ref(event.get("chapter_id", ""), event.get("block_id", ""), item) for item in event.get("evidence", [])[:3]]
        return {
            "name": event.get("summary", "")[:32] or event.get("event_id", "剧情事件"),
            "label": preferred_entity_label(ontology, "PlotEvent", "Conflict", fallback="PlotEvent"),
            "summary": event.get("summary", ""),
            "attributes": {"event_id": event.get("event_id", ""), "chapter_id": event.get("chapter_id", "")},
            "evidence_refs": snippets,
        }

    def _rule_candidate(self, ontology: Dict[str, Any], rule_text: str) -> Dict[str, Any]:
        label = preferred_entity_label(ontology, "RuleSystem", "CultivationSystem", "MysticalSystem", fallback="RuleSystem")
        return {
            "name": rule_text[:24] or "世界规则",
            "label": label,
            "summary": rule_text,
            "attributes": {"rule_text": rule_text, "aliases": []},
            "evidence_refs": [evidence_ref(snippet=rule_text)],
        }

    def _raw_candidates(self, ontology: Dict[str, Any], extracted_text: str, registry: Dict[str, Any]) -> List[Dict[str, Any]]:
        known = {normalize_name(name) for name in registry}
        sentences = split_sentences(extracted_text)
        candidates = []
        for name in find_artifact_candidates(extracted_text):
            if normalize_name(name) in known:
                continue
            evidence = [evidence_ref(snippet=item) for item in sentences if name in item][:3]
            candidates.append({"name": name, "label": preferred_entity_label(ontology, "Artifact", "KnowledgeItem", fallback="Artifact"), "summary": evidence[0].snippet if evidence else name, "attributes": {"aliases": []}, "evidence_refs": evidence})
        return candidates

    def _merge_node_candidates(self, project_id: str, candidates: Sequence[Dict[str, Any]]) -> List[GraphNode]:
        merged: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for item in candidates:
            key = (item["label"], normalize_name(item["name"]))
            record = merged.setdefault(key, {"name": item["name"], "label": item["label"], "summary": "", "attributes": {}, "evidence_refs": []})
            record["summary"] = item["summary"] if len(item["summary"]) > len(record["summary"]) else record["summary"]
            record["attributes"] = {**record["attributes"], **item.get("attributes", {})}
            aliases = unique_strings(record["attributes"].get("aliases", []) + item.get("attributes", {}).get("aliases", []))
            record["attributes"]["aliases"] = aliases
            record["evidence_refs"].extend(item.get("evidence_refs", []))
        return [
            GraphNode(
                uuid=node_uuid(project_id, item["label"], item["name"]),
                name=item["name"],
                labels=labels_for_entity(item["label"]),
                summary=item["summary"] or item["name"],
                attributes=item["attributes"],
                evidence_refs=dedupe_evidence(item["evidence_refs"]),
            )
            for item in merged.values()
        ]

    def _relationship_edges(self, ontology: Dict[str, Any], story_memory: Dict[str, Any], lookup: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
        edges = []
        for item in story_memory.get("relationship_ledger", []):
            source_uuid = self._resolve_entity_uuid(lookup, item.get("source", ""))
            target_uuid = self._resolve_entity_uuid(lookup, item.get("target", ""))
            if not source_uuid or not target_uuid:
                continue
            latest = (item.get("changes") or [{}])[-1]
            name = self._relationship_edge_name(ontology, latest.get("change", "co_occurrence"))
            evidence = [evidence_ref(change.get("chapter_id", ""), change.get("block_id", ""), snippet) for change in item.get("changes", []) for snippet in change.get("evidence", [])[:1]]
            edges.append({"name": name, "fact": latest.get("change", "关系变化"), "source_uuid": source_uuid, "target_uuid": target_uuid, "attributes": {"change": latest.get("change", "co_occurrence")}, "weight": len(item.get("changes", [])) or 1, "evidence_refs": evidence})
        return edges

    def _event_edges(self, ontology: Dict[str, Any], story_memory: Dict[str, Any], lookup: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
        edges = []
        for event in story_memory.get("event_timeline", []):
            event_uuid = self._uuid_by_attribute(lookup, "event_id", event.get("event_id", ""))
            if not event_uuid:
                continue
            names = list(event.get("characters", [])) + list(event.get("organizations", []))
            for name in unique_strings(names):
                actor_uuid = self._resolve_entity_uuid(lookup, name)
                if not actor_uuid:
                    continue
                evidence = [evidence_ref(event.get("chapter_id", ""), event.get("block_id", ""), item) for item in event.get("evidence", [])[:2]]
                edges.append({"name": preferred_edge_name(ontology, "PARTICIPATES_IN", "INVOLVED_IN", fallback=DEFAULT_EVENT_EDGE), "fact": event.get("summary", ""), "source_uuid": actor_uuid, "target_uuid": event_uuid, "attributes": {"chapter_id": event.get("chapter_id", "")}, "weight": 1, "evidence_refs": evidence})
            for location_name in cooccurring_names(event.get("summary", ""), lookup.get("Location", {}).keys()):
                location_uuid = lookup.get("Location", {}).get(location_name)
                if not location_uuid:
                    continue
                edges.append({"name": preferred_edge_name(ontology, "LOCATED_IN", "TAKES_PLACE_IN", fallback=DEFAULT_LOCATION_EDGE), "fact": event.get("summary", ""), "source_uuid": event_uuid, "target_uuid": location_uuid, "attributes": {}, "weight": 1, "evidence_refs": [evidence_ref(event.get("chapter_id", ""), event.get("block_id", ""), event.get("summary", ""))]})
        return edges

    def _artifact_edges(self, ontology: Dict[str, Any], extracted_text: str, lookup: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
        edges = []
        artifact_names = list(lookup.get("Artifact", {}).keys()) + list(lookup.get("KnowledgeItem", {}).keys())
        entity_names = list(lookup.get("Character", {}).keys()) + list(lookup.get("Organization", {}).keys())
        for sentence in split_sentences(extracted_text):
            artifacts = cooccurring_names(sentence, artifact_names)
            entities = cooccurring_names(sentence, entity_names)
            if not artifacts or not entities:
                continue
            for source_name in entities[:2]:
                for target_name in artifacts[:2]:
                    source_uuid = self._resolve_entity_uuid(lookup, source_name)
                    target_uuid = self._resolve_entity_uuid(lookup, target_name)
                    if source_uuid and target_uuid:
                        edges.append({"name": preferred_edge_name(ontology, "POSSESSES", "SEEKS", "UTILIZES_KNOWLEDGE", fallback=DEFAULT_ARTIFACT_EDGE), "fact": sentence[:180], "source_uuid": source_uuid, "target_uuid": target_uuid, "attributes": {}, "weight": 1, "evidence_refs": [evidence_ref(snippet=sentence)]})
        return edges

    def _rule_edges(self, ontology: Dict[str, Any], story_memory: Dict[str, Any], lookup: Dict[str, Dict[str, str]]) -> List[Dict[str, Any]]:
        edges = []
        entity_names = list(lookup.get("Character", {}).keys()) + list(lookup.get("Organization", {}).keys())
        for rule_text in story_memory.get("world_rules", []):
            rule_uuid = self._uuid_by_attribute(lookup, "rule_text", rule_text)
            if not rule_uuid:
                continue
            for name in cooccurring_names(rule_text, entity_names):
                source_uuid = self._resolve_entity_uuid(lookup, name)
                if source_uuid:
                    edges.append({"name": preferred_edge_name(ontology, "OBEYS_RULE", "PRACTICES", fallback=DEFAULT_RULE_EDGE), "fact": rule_text, "source_uuid": source_uuid, "target_uuid": rule_uuid, "attributes": {}, "weight": 1, "evidence_refs": [evidence_ref(snippet=rule_text)]})
        return edges

    def _merge_edge_candidates(self, project_id: str, candidates: Sequence[Dict[str, Any]]) -> List[GraphEdge]:
        merged: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for item in candidates:
            key = (item["name"], item["source_uuid"], item["target_uuid"])
            record = merged.setdefault(key, {"fact": "", "attributes": {}, "weight": 0, "evidence_refs": []})
            record["fact"] = item["fact"] if len(item["fact"]) > len(record["fact"]) else record["fact"]
            record["attributes"] = {**record["attributes"], **item.get("attributes", {})}
            record["weight"] += int(item.get("weight", 1))
            record["evidence_refs"].extend(item.get("evidence_refs", []))
        return [
            GraphEdge(uuid=edge_uuid(project_id, name, source_uuid, target_uuid), name=name, fact=item["fact"], source_node_uuid=source_uuid, target_node_uuid=target_uuid, attributes=item["attributes"], weight=item["weight"], evidence_refs=dedupe_evidence(item["evidence_refs"]))
            for (name, source_uuid, target_uuid), item in merged.items()
        ]

    def _entity_evidence(self, name: str, packets: Sequence[Dict[str, Any]], fallbacks: Sequence[str]) -> List[EvidenceRef]:
        evidence = [evidence_ref(packet.get("owned_chapters", [""])[0], packet.get("block_id", ""), snippet) for packet in packets for entity in packet.get("local_entities", []) if entity.get("name") == name for snippet in entity.get("evidence", [])[:2]]
        return evidence or [evidence_ref(snippet=item) for item in list(fallbacks)[:3]]

    def _should_add_faction(self, item: Dict[str, Any], name: str, ontology: Dict[str, Any]) -> bool:
        if not any(str(entity.get("name")) == "Faction" for entity in ontology.get("entity_types", [])):
            return False
        org_type = str(item.get("organization_type", "")).lower()
        return org_type in {"alliance", "association", "group", "consortium", "kingdom", "dynasty"} or any(token in name for token in ("盟", "会", "阵营", "王朝"))

    def _node_lookup(self, nodes: Sequence[GraphNode]) -> Dict[str, Dict[str, str]]:
        lookup: Dict[str, Dict[str, str]] = {"_attrs": {}}
        for node in nodes:
            entity_type = next((label for label in node.labels if label not in {"Entity", "Node"}), "")
            lookup.setdefault(entity_type, {})[node.name] = node.uuid
            for key, value in node.attributes.items():
                if value:
                    lookup["_attrs"][f"{key}:{value}"] = node.uuid
        return lookup

    def _resolve_entity_uuid(self, lookup: Dict[str, Dict[str, str]], name: str) -> str:
        for label in ("Character", "Organization", "Faction", "Location", "Artifact", "KnowledgeItem"):
            if name in lookup.get(label, {}):
                return lookup[label][name]
        return ""

    def _uuid_by_attribute(self, lookup: Dict[str, Dict[str, str]], key: str, value: str) -> str:
        return lookup.get("_attrs", {}).get(f"{key}:{value}", "")

    def _relationship_edge_name(self, ontology: Dict[str, Any], change: str) -> str:
        mapping = {
            "ally": ("ALLIED_WITH", "ALLY_WITH", "COOPERATES_WITH"),
            "conflict": ("CONFLICTS_WITH", "HOSTILE_TO", "THREATENS"),
            "affiliation": ("BELONGS_TO", "MEMBER_OF", "LOYAL_TO"),
        }
        return preferred_edge_name(ontology, *(mapping.get(change, tuple())), fallback=DEFAULT_RELATIONSHIP_EDGE)
