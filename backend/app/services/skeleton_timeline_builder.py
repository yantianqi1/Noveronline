"""顺序构建小说骨架时间线。"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from .local_block_fact_support import split_sentences
from .novel_seed_analyzer import CHARACTER_STOP_WORDS, ORG_SUFFIX_TO_TYPE, NovelSeedAnalyzer
from .organization_candidate_filter import is_valid_org_candidate


DIALOGUE_SUFFIXES = (
    "说道",
    "问道",
    "答道",
    "开口",
    "沉声",
    "低声",
    "笑道",
    "冷笑",
)
ORG_LEADING_NOISE_CHARS = set("来去见过向于在从将把被和与同对再仍又都先正会要想说问答")


class SkeletonTimelineBuilder:
    """基于现有正则分析器顺序扫描章节，生成全文骨架。"""

    def __init__(self, analyzer: NovelSeedAnalyzer):
        self.analyzer = analyzer

    def build(self, chapters: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        ordered = sorted(chapters, key=lambda item: item.get("order", 0))
        character_index: Dict[str, Dict[str, Any]] = {}
        organization_index: Dict[str, Dict[str, Any]] = {}
        chapter_sketches = []
        for chapter in ordered:
            analysis = self.analyzer.analyze_text(chapter["content"])
            organizations = self._chapter_organizations(analysis.get("organizations", []))
            organization_names = {item["name"] for item in organizations}
            characters = self._chapter_characters(analysis.get("characters", []), organization_names)
            chapter_sketches.append(self._chapter_sketch(chapter, characters, organizations))
            self._accumulate_entities(character_index, characters, chapter)
            self._accumulate_entities(organization_index, organizations, chapter)
        return {
            "chapter_count": len(ordered),
            "global_characters": self._sorted_entities(character_index),
            "global_organizations": self._sorted_entities(organization_index),
            "chapter_sketches": chapter_sketches,
            "character_arcs": self._character_arcs(character_index),
        }

    def _chapter_sketch(
        self,
        chapter: Dict[str, Any],
        characters: List[Dict[str, Any]],
        organizations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        character_names = [item["name"] for item in characters]
        return {
            "chapter_id": chapter["chapter_id"],
            "order": chapter.get("order", 0),
            "title": chapter.get("title", chapter["chapter_id"]),
            "characters": character_names,
            "organizations": [item["name"] for item in organizations],
            "fingerprint": self._chapter_fingerprint(chapter, character_names),
            "tail_hook": self._chapter_tail_hook(chapter),
        }

    def _chapter_fingerprint(self, chapter: Dict[str, Any], character_names: Sequence[str]) -> str:
        sentences = split_sentences(chapter.get("content", ""))
        if not sentences:
            return chapter.get("title", chapter["chapter_id"])
        opening = sentences[0][:100]
        core = self._core_sentence(sentences, character_names)[:100]
        if not core or core == opening:
            return opening
        return f"{opening}；{core}"

    def _chapter_tail_hook(self, chapter: Dict[str, Any]) -> str:
        sentences = split_sentences(chapter.get("content", ""))
        if not sentences:
            return chapter.get("title", chapter["chapter_id"])
        tail = sentences[-2:] if len(sentences) > 1 else sentences
        return "；".join(tail)[:120]

    def _core_sentence(self, sentences: Sequence[str], character_names: Sequence[str]) -> str:
        if len(sentences) <= 1:
            return sentences[0]
        middle = sentences[1:-1] or sentences[1:]
        return max(middle, key=lambda sentence: self._character_hits(sentence, character_names))

    def _character_hits(self, sentence: str, character_names: Sequence[str]) -> int:
        return sum(1 for name in character_names if name and name in sentence)

    def _chapter_characters(
        self,
        records: Sequence[Dict[str, Any]],
        organization_names: set[str],
    ) -> List[Dict[str, Any]]:
        merged = defaultdict(int)
        for item in records:
            name = self._clean_character_name(item.get("name", ""), organization_names)
            if not name:
                continue
            merged[name] += int(item.get("mention_count", 1))
        return [{"name": name, "mention_count": count} for name, count in merged.items()]

    def _chapter_organizations(self, records: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged = defaultdict(int)
        for item in records:
            name = self._clean_organization_name(item.get("name", ""))
            if not name:
                continue
            merged[name] += int(item.get("mention_count", 1))
        shadowed = self._shadowed_organization_names(list(merged.keys()))
        return [
            {"name": name, "mention_count": count}
            for name, count in merged.items()
            if name not in shadowed
        ]

    def _accumulate_entities(
        self,
        bucket: Dict[str, Dict[str, Any]],
        items: Sequence[Dict[str, Any]],
        chapter: Dict[str, Any],
    ) -> None:
        for item in items:
            payload = bucket.setdefault(
                item["name"],
                {
                    "name": item["name"],
                    "chapter_ids": [],
                    "chapter_orders": [],
                    "mention_count": 0,
                    "appearance_count": 0,
                },
            )
            payload["mention_count"] += item.get("mention_count", 0)
            if chapter["chapter_id"] in payload["chapter_ids"]:
                continue
            payload["chapter_ids"].append(chapter["chapter_id"])
            payload["chapter_orders"].append(chapter.get("order", 0))
            payload["appearance_count"] += 1

    def _sorted_entities(self, bucket: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        return sorted(
            bucket.values(),
            key=lambda item: (-item["appearance_count"], -item["mention_count"], item["name"]),
        )

    def _character_arcs(self, bucket: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
        arcs = []
        for item in self._sorted_entities(bucket):
            arcs.append(
                {
                    "name": item["name"],
                    "first_chapter_id": item["chapter_ids"][0] if item["chapter_ids"] else "",
                    "last_chapter_id": item["chapter_ids"][-1] if item["chapter_ids"] else "",
                    "appearance_count": item["appearance_count"],
                }
            )
        return arcs

    def _clean_character_name(self, raw_name: str, organization_names: set[str]) -> Optional[str]:
        name = raw_name.strip()
        for suffix in DIALOGUE_SUFFIXES:
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        if len(name) < 2 or len(name) > 4:
            return None
        if name in CHARACTER_STOP_WORDS:
            return None
        if any(suffix in name for suffix in ORG_SUFFIX_TO_TYPE):
            return None
        if name in organization_names:
            return None
        return name

    def _clean_organization_name(self, raw_name: str) -> Optional[str]:
        name = raw_name.strip()
        suffix = self._matched_suffix(name)
        if not suffix:
            return None
        end = name.find(suffix) + len(suffix)
        canonical = self._trim_org_leading_noise(name[:end])
        if not is_valid_org_candidate(canonical):
            return None
        return canonical

    def _shadowed_organization_names(self, names: Sequence[str]) -> set[str]:
        shadowed = set()
        for name in names:
            for other in names:
                if name == other or len(other) <= len(name):
                    continue
                if other.endswith(name):
                    shadowed.add(name)
        return shadowed

    def _matched_suffix(self, name: str) -> Optional[str]:
        for suffix in sorted(ORG_SUFFIX_TO_TYPE, key=len, reverse=True):
            if suffix in name:
                return suffix
        return None

    def _trim_org_leading_noise(self, name: str) -> str:
        cleaned = name
        while len(cleaned) > 2 and cleaned[0] in ORG_LEADING_NOISE_CHARS:
            cleaned = cleaned[1:]
        return cleaned
