"""本地图谱构建辅助函数。"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Sequence

from .local_story_graph_models import EvidenceRef


LOCAL_GRAPH_PREFIX = "local_graph_"
ENTITY_LABEL_BASE = "Entity"
NODE_LABEL_BASE = "Node"
DEFAULT_EVENT_EDGE = "PARTICIPATES_IN"
DEFAULT_LOCATION_EDGE = "LOCATED_IN"
DEFAULT_RULE_EDGE = "OBEYS_RULE"
DEFAULT_RELATIONSHIP_EDGE = "RELATES_TO"
DEFAULT_ARTIFACT_EDGE = "POSSESSES"

LOCATION_SUFFIXES = ("谷", "城", "山", "门", "塔", "殿", "宫", "湖", "峰", "府", "楼", "院", "关", "河")
ARTIFACT_KEYWORDS = ("引擎", "密信", "钥匙", "铜片", "玉简", "令牌", "卷轴", "法器", "阵图", "请帖", "药箱")
LOCATION_CONTEXT_PREFIXES = (
    "送入",
    "来到",
    "抵达",
    "前往",
    "回到",
    "进入",
    "走进",
    "身处",
    "位于",
    "待在",
    "留在",
    "住在",
    "赶到",
    "藏在",
    "困在",
    "守在",
    "驻守",
    "从",
    "到",
    "去",
    "在",
    "入",
)


def stable_hash(*parts: str) -> str:
    joined = "::".join(parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def local_graph_id(project_id: str) -> str:
    return f"{LOCAL_GRAPH_PREFIX}{project_id}"


def project_id_from_graph_id(graph_id: str) -> str:
    if graph_id.startswith(LOCAL_GRAPH_PREFIX):
        return graph_id[len(LOCAL_GRAPH_PREFIX):]
    return graph_id


def node_uuid(project_id: str, label: str, name: str) -> str:
    return f"node::{project_id}::{stable_hash(label, normalize_name(name))}"


def edge_uuid(project_id: str, name: str, source_uuid: str, target_uuid: str) -> str:
    return f"edge::{project_id}::{stable_hash(name, source_uuid, target_uuid)}"


def normalize_name(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or ""))
    return text.strip().lower()


def unique_strings(items: Iterable[str]) -> List[str]:
    seen = set()
    values: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values


def dedupe_evidence(items: Sequence[EvidenceRef]) -> List[EvidenceRef]:
    seen = set()
    values: List[EvidenceRef] = []
    for item in items:
        key = (item.chapter_id, item.block_id, item.snippet)
        if key in seen:
            continue
        seen.add(key)
        values.append(item)
    return values


def preferred_entity_label(ontology: Dict[str, Any], *candidates: str, fallback: str) -> str:
    available = {str(item.get("name") or ""): item for item in ontology.get("entity_types", [])}
    for candidate in candidates:
        if candidate in available:
            return candidate
    return fallback


def preferred_edge_name(ontology: Dict[str, Any], *candidates: str, fallback: str) -> str:
    available = {str(item.get("name") or "") for item in ontology.get("edge_types", [])}
    for candidate in candidates:
        if candidate in available:
            return candidate
    return fallback


def evidence_ref(chapter_id: str = "", block_id: str = "", snippet: str = "") -> EvidenceRef:
    return EvidenceRef(
        chapter_id=str(chapter_id or ""),
        block_id=str(block_id or ""),
        snippet=str(snippet or "").strip(),
    )


def labels_for_entity(entity_label: str) -> List[str]:
    return [ENTITY_LABEL_BASE, NODE_LABEL_BASE, entity_label]


def split_sentences(text: str) -> List[str]:
    pieces = re.split(r"[。！？!?]\s*|\n+", str(text or ""))
    return [piece.strip(" \n\t，,；;") for piece in pieces if piece.strip()]


def find_location_candidates(text: str) -> List[str]:
    suffixes = "|".join(sorted(LOCATION_SUFFIXES, key=len, reverse=True))
    prefixes = "|".join(sorted(LOCATION_CONTEXT_PREFIXES, key=len, reverse=True))
    context_pattern = re.compile(rf"(?:{prefixes})([\u4e00-\u9fff]{{2,12}})(?=$|[，,；;、])")
    location_pattern = re.compile(rf"([\u4e00-\u9fff]{{1,12}}(?:{suffixes}))")
    candidates: List[str] = []
    for sentence in split_sentences(text):
        for match in context_pattern.finditer(sentence):
            window = match.group(1)
            location_match = location_pattern.search(window)
            if location_match:
                candidates.append(location_match.group(1))
    return unique_strings(candidates)


def find_artifact_candidates(text: str) -> List[str]:
    keywords = "|".join(sorted(ARTIFACT_KEYWORDS, key=len, reverse=True))
    pattern = re.compile(rf"([\u4e00-\u9fffA-Za-z0-9]{{0,6}}(?:{keywords}))")
    return unique_strings(match.group(1) for match in pattern.finditer(text))


def cooccurring_names(text: str, names: Sequence[str]) -> List[str]:
    return [item for item in unique_strings(names) if item and item in text]
