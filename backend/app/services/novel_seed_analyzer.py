"""
离线小说种子分析器
在无 LLM / 无图谱服务时，基于规则从小说文本中提取角色、组织与关系。
"""

import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Sequence, Tuple

from .genre_plugin import (
    DEFAULT_CHARACTER_STOP_WORDS,
    DEFAULT_ORG_SUFFIX_TO_TYPE,
    DEFAULT_RELATION_KEYWORDS,
    merge_relation_keywords,
    resolve_genre_plugin,
)
from .organization_candidate_filter import is_valid_org_candidate

ORG_SUFFIX_TO_TYPE = DEFAULT_ORG_SUFFIX_TO_TYPE
CHARACTER_STOP_WORDS = DEFAULT_CHARACTER_STOP_WORDS
RELATION_KEYWORDS = DEFAULT_RELATION_KEYWORDS


class NovelSeedAnalyzer:
    CHARACTER_PATTERNS = [
        re.compile(r"(?:名叫|叫做|叫|少年|少女|青年|女子|男人|女人|弟子|长老|掌柜|先生|师兄|师姐|师父|宗主|城主|皇帝|公主|殿下|司长|队长|博士|工程师|侍从|侍卫)([\u4e00-\u9fff]{2,4})"),
        re.compile(r"([\u4e00-\u9fff]{2,4})(?:说道|问道|答道|开口|沉声道|低声道|笑道|冷笑|看着|望着|点头|摇头|抬手|转身|跪下|起身|走进|回头|叹道|命令道)"),
        re.compile(r"([\u4e00-\u9fff]{2,4})[：:]"),
        re.compile(r"([\u4e00-\u9fff]{2,4})(?=在|与|和|向|对|替|把|被|将|让|令|需|要|会|能|想|正|忽然|必须|决定|提醒|意识到|同时|站在|看着|望着)"),
        re.compile(r"(?:^|[，,、\n])([\u4e00-\u9fff]{2,4})(?=[、，,与和])"),
    ]

    def __init__(self, genre: str = "default"):
        plugin = resolve_genre_plugin(genre)
        self.character_stop_words = frozenset(CHARACTER_STOP_WORDS | plugin.get_character_stop_words())
        self.org_suffix_to_type = {**ORG_SUFFIX_TO_TYPE, **plugin.get_organization_suffixes()}
        self.relation_keywords = merge_relation_keywords(RELATION_KEYWORDS, plugin.get_relation_keywords())
        self.org_pattern = self._build_org_pattern()

    def analyze_document_texts(
        self,
        document_texts: Sequence[str],
        analysis_goal: str = "",
        project_name: str = "",
    ) -> Dict[str, Any]:
        return self.analyze_text(
            text="\n\n".join(document_texts),
            analysis_goal=analysis_goal,
            project_name=project_name,
        )

    def analyze_text(self, text: str, analysis_goal: str = "", project_name: str = "") -> Dict[str, Any]:
        normalized = self._normalize_text(text)
        sentences = self._split_sentences(normalized)
        organizations = self._extract_organizations(normalized, sentences)
        organization_names = {item["name"] for item in organizations}
        characters = self._extract_characters(normalized, sentences, organization_names)
        relations = self._extract_relations(sentences, characters, organizations)
        chapters = self._build_chapter_beats(sentences)

        summary = (
            f"已离线提取 {len(characters)} 名角色、{len(organizations)} 个组织/势力、"
            f"{len(relations)} 条关系，适合后续档案生成与世界线推演。"
        )

        return {
            "project_name": project_name,
            "analysis_goal": analysis_goal,
            "characters": characters,
            "organizations": organizations,
            "relations": relations,
            "chapter_beats": chapters,
            "analysis_summary": summary,
            "source_stats": {
                "text_length": len(normalized),
                "sentence_count": len(sentences),
                "character_count": len(characters),
                "organization_count": len(organizations),
                "relation_count": len(relations),
            },
        }

    def _normalize_text(self, text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _split_sentences(self, text: str) -> List[str]:
        pieces = re.split(r"[。！？!?]\s*|\n+", text)
        return [piece.strip(" \n\t，,；;") for piece in pieces if piece.strip()]

    def _extract_organizations(self, text: str, sentences: Sequence[str]) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        evidence: Dict[str, List[str]] = defaultdict(list)

        for match in self.org_pattern.finditer(text):
            name = self._canonical_org_name(match.group(1).strip())
            if not is_valid_org_candidate(name):
                continue
            counter[name] += 1

        for sentence in sentences:
            for name in counter:
                if name in sentence and len(evidence[name]) < 3:
                    evidence[name].append(sentence[:80])

        records = []
        for name, count in counter.most_common():
            suffix = self._match_org_suffix(name)
            records.append({
                "name": name,
                "mention_count": count,
                "importance_tier": self._importance_tier(count, rank=len(records)),
                "organization_type": self.org_suffix_to_type.get(suffix, "organization"),
                "summary": self._summarize_org(name, evidence.get(name, [])),
                "evidence": evidence.get(name, []),
            })
        return records

    def _extract_characters(
        self,
        text: str,
        sentences: Sequence[str],
        organization_names: set,
    ) -> List[Dict[str, Any]]:
        counter: Counter[str] = Counter()
        evidence: Dict[str, List[str]] = defaultdict(list)

        for pattern in self.CHARACTER_PATTERNS:
            for match in pattern.finditer(text):
                name = match.group(1).strip()
                if not self._looks_like_character(name, organization_names):
                    continue
                counter[name] += 1

        for sentence in sentences:
            for name in list(counter.keys()):
                if name in sentence and len(evidence[name]) < 4:
                    evidence[name].append(sentence[:90])

        ranked = counter.most_common()
        records = []
        for idx, (name, count) in enumerate(ranked):
            records.append({
                "name": name,
                "mention_count": count,
                "importance_tier": self._importance_tier(count, idx),
                "identity_hint": self._infer_identity(evidence.get(name, [])),
                "profile_summary": self._summarize_character(name, evidence.get(name, [])),
                "evidence": evidence.get(name, []),
            })
        return records

    def _extract_relations(
        self,
        sentences: Sequence[str],
        characters: Sequence[Dict[str, Any]],
        organizations: Sequence[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        entity_names = [item["name"] for item in characters] + [item["name"] for item in organizations]
        pair_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for sentence in sentences:
            present = [name for name in entity_names if name in sentence]
            if len(present) < 2:
                continue

            relation_type = self._infer_relation_type(sentence)
            for i in range(len(present)):
                for j in range(i + 1, len(present)):
                    source, target = sorted((present[i], present[j]))
                    key = (source, target)
                    if key not in pair_map:
                        pair_map[key] = {
                            "source": source,
                            "target": target,
                            "relation_type": relation_type,
                            "weight": 0,
                            "evidence": [],
                        }
                    pair_map[key]["weight"] += 1
                    if len(pair_map[key]["evidence"]) < 3:
                        pair_map[key]["evidence"].append(sentence[:100])
                    if pair_map[key]["relation_type"] == "co_occurrence" and relation_type != "co_occurrence":
                        pair_map[key]["relation_type"] = relation_type

        return sorted(pair_map.values(), key=lambda item: (-item["weight"], item["source"], item["target"]))

    def _build_chapter_beats(self, sentences: Sequence[str]) -> List[Dict[str, Any]]:
        beats = []
        for idx, sentence in enumerate(sentences[:8], start=1):
            beats.append({
                "beat_id": f"beat_{idx}",
                "title": f"剧情节点 {idx}",
                "summary": sentence[:120],
            })
        return beats

    def _looks_like_character(self, name: str, organization_names: set) -> bool:
        if name in self.character_stop_words or name in organization_names:
            return False
        if len(name) < 2 or len(name) > 4:
            return False
        if self._match_org_suffix(name):
            return False
        if any(word in name for word in ("什么", "这样", "那个", "这个", "一名", "一种")):
            return False
        return True

    def _match_org_suffix(self, name: str) -> str:
        for suffix in sorted(self.org_suffix_to_type.keys(), key=len, reverse=True):
            if name.endswith(suffix):
                return suffix
        return ""

    def _canonical_org_name(self, name: str) -> str:
        candidates = []
        for suffix in sorted(self.org_suffix_to_type.keys(), key=len, reverse=True):
            index = name.find(suffix)
            if index >= 0:
                candidates.append((len(suffix), name[:index + len(suffix)]))
        if not candidates:
            return name
        _, canonical = max(candidates, key=lambda item: (item[0], -len(item[1])))
        return canonical

    def _build_org_pattern(self) -> re.Pattern[str]:
        suffixes = "|".join(sorted(map(re.escape, self.org_suffix_to_type), key=len, reverse=True))
        return re.compile(rf"(?=([\u4e00-\u9fff]{{1,4}}(?:{suffixes})))")

    def _importance_tier(self, count: int, rank: int) -> str:
        if rank == 0 or count >= 8:
            return "protagonist"
        if rank <= 2 or count >= 5:
            return "major"
        if count >= 2:
            return "supporting"
        return "minor"

    def _infer_identity(self, snippets: Sequence[str]) -> str:
        joined = " ".join(snippets)
        for keyword, identity in (
            ("宗主", "宗门核心人物"),
            ("长老", "高层修行者"),
            ("司长", "机构掌权者"),
            ("博士", "研究者"),
            ("队长", "行动领队"),
            ("公主", "王室成员"),
            ("掌柜", "经营者"),
            ("弟子", "门下弟子"),
        ):
            if keyword in joined:
                return identity
        return "关键角色"

    def _summarize_character(self, name: str, snippets: Sequence[str]) -> str:
        if not snippets:
            return f"{name} 在故事中已有命名出场，适合作为独立角色节点。"
        return f"{name} 常出现在这些情境中：" + "；".join(snippets[:2])

    def _summarize_org(self, name: str, snippets: Sequence[str]) -> str:
        if not snippets:
            return f"{name} 是故事中的已命名组织或势力。"
        return f"{name} 的核心活动线索：" + "；".join(snippets[:2])

    def _infer_relation_type(self, sentence: str) -> str:
        for relation_type, keywords in self.relation_keywords.items():
            if any(keyword in sentence for keyword in keywords):
                return relation_type
        return "co_occurrence"
