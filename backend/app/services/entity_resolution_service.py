"""全局实体消歧服务。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..utils.llm_client import LLMClient
from ..utils.llm_json import normalize_json_object
from .entity_resolution_line_protocol import EntityResolutionLineProtocolExecutor
from .entity_resolution_prompts import ENTITY_RESOLUTION_SYSTEM_PROMPT
from .llm_router import LlmRouter
from .seed_stage_fallback_support import should_use_rule_fallback


class EntityResolutionService:
    """并发提取后的保守实体消歧。"""

    MODULE_KEY = "entity_resolution"

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        llm_router: Optional[LlmRouter] = None,
    ):
        self.llm_client = llm_client
        self.llm_router = llm_router or LlmRouter()

    def resolve(self, story_memory: Dict[str, Any]) -> Dict[str, Any]:
        registry = {name: self._copy_entity(entity) for name, entity in story_memory.get("entity_registry", {}).items()}
        alias_map = dict(story_memory.get("alias_map", {}))
        registry, alias_map = self._merge_known_aliases(registry, alias_map)
        candidates = self._find_merge_candidates(registry)
        registry, alias_map = self._resolve_candidates(registry, alias_map, candidates)
        return {**story_memory, "entity_registry": registry, "alias_map": alias_map}

    def _merge_known_aliases(
        self,
        registry: Dict[str, Dict[str, Any]],
        alias_map: Dict[str, str],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        for alias, canonical in list(alias_map.items()):
            if alias == canonical or canonical not in registry:
                continue
            if alias in registry:
                self._merge_entities(registry, alias_map, canonical, alias)
                continue
            aliases = registry[canonical].setdefault("aliases", [])
            if alias not in aliases:
                aliases.append(alias)
        return registry, alias_map

    def _find_merge_candidates(self, registry: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str, str]]:
        names = sorted(registry)
        candidates = []
        for index, name_a in enumerate(names):
            for name_b in names[index + 1:]:
                match_type = self._match_type(name_a, name_b)
                if match_type:
                    candidates.append((name_a, name_b, match_type))
        return candidates

    def _match_type(self, name_a: str, name_b: str) -> str:
        if len(name_a) >= 2 and len(name_b) >= 2 and (name_a in name_b or name_b in name_a):
            return "substring"
        if self._edit_distance(name_a, name_b) <= 1:
            return "typo"
        return ""

    def _resolve_candidates(
        self,
        registry: Dict[str, Dict[str, Any]],
        alias_map: Dict[str, str],
        candidates: Sequence[Tuple[str, str, str]],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        if not candidates:
            return registry, alias_map
        client = self.llm_client or self.llm_router.build_client(self.MODULE_KEY)
        for name_a, name_b, match_type in candidates:
            if name_a not in registry or name_b not in registry:
                continue
            decision = self._llm_decision(client, name_a, registry[name_a], name_b, registry[name_b], match_type)
            if not decision.get("merge"):
                continue
            confidence = decision.get("confidence", 1 if decision.get("merge") else 0)
            if confidence < 0.7:
                continue
            canonical = decision.get("canonical_name") or name_a
            alias = name_b if canonical == name_a else name_a
            self._merge_entities(registry, alias_map, canonical, alias)
        return registry, alias_map

    def _llm_decision(
        self,
        client: LLMClient,
        name_a: str,
        entity_a: Dict[str, Any],
        name_b: str,
        entity_b: Dict[str, Any],
        match_type: str,
    ) -> Dict[str, Any]:
        try:
            if hasattr(client, "chat"):
                return EntityResolutionLineProtocolExecutor(client).decide(
                    ENTITY_RESOLUTION_SYSTEM_PROMPT,
                    self._build_prompt(name_a, entity_a, name_b, entity_b, match_type),
                )
            payload = client.chat_json_value(
                messages=[
                    {"role": "system", "content": ENTITY_RESOLUTION_SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_prompt(name_a, entity_a, name_b, entity_b, match_type)},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            return normalize_json_object(payload, "实体消歧")
        except Exception as exc:
            if not should_use_rule_fallback(exc):
                raise
            return {"merge": False, "canonical_name": "", "confidence": 0, "reason": str(exc)}

    def _build_prompt(
        self,
        name_a: str,
        entity_a: Dict[str, Any],
        name_b: str,
        entity_b: Dict[str, Any],
        match_type: str,
    ) -> str:
        return (
            f"候选匹配类型：{match_type}\n\n"
            f"实体A：{name_a}\n"
            f"类型：{entity_a.get('entity_type', 'unknown')}\n"
            f"摘要：{entity_a.get('summary', '')}\n"
            f"证据：{entity_a.get('evidence', [])[:3]}\n"
            f"出现块：{entity_a.get('mention_blocks', [])}\n\n"
            f"实体B：{name_b}\n"
            f"类型：{entity_b.get('entity_type', 'unknown')}\n"
            f"摘要：{entity_b.get('summary', '')}\n"
            f"证据：{entity_b.get('evidence', [])[:3]}\n"
            f"出现块：{entity_b.get('mention_blocks', [])}"
        )

    def _merge_entities(
        self,
        registry: Dict[str, Dict[str, Any]],
        alias_map: Dict[str, str],
        canonical: str,
        alias: str,
    ) -> None:
        if canonical not in registry or alias not in registry:
            return
        target = registry[canonical]
        source = registry.pop(alias)
        target["mention_blocks"] = sorted(set(target.get("mention_blocks", []) + source.get("mention_blocks", [])))
        target["aliases"] = sorted(set(target.get("aliases", []) + source.get("aliases", []) + [alias]))
        target["evidence"] = self._merge_list(target.get("evidence", []), source.get("evidence", []), 6)
        if source.get("summary") and not target.get("summary"):
            target["summary"] = source["summary"]
        alias_map[alias] = canonical
        for alias_name in source.get("aliases", []):
            alias_map[alias_name] = canonical

    def _merge_list(self, left: Sequence[str], right: Sequence[str], limit: int) -> List[str]:
        merged = []
        for item in list(left) + list(right):
            if item in merged:
                continue
            merged.append(item)
            if len(merged) >= limit:
                break
        return merged

    def _copy_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        return {
            **entity,
            "aliases": list(entity.get("aliases", [])),
            "mention_blocks": list(entity.get("mention_blocks", [])),
            "evidence": list(entity.get("evidence", [])),
        }

    def _edit_distance(self, left: str, right: str) -> int:
        if left == right:
            return 0
        if abs(len(left) - len(right)) > 1:
            return 2
        previous = list(range(len(right) + 1))
        for i, left_char in enumerate(left, start=1):
            current = [i]
            for j, right_char in enumerate(right, start=1):
                insert_cost = current[j - 1] + 1
                delete_cost = previous[j] + 1
                replace_cost = previous[j - 1] + (left_char != right_char)
                current.append(min(insert_cost, delete_cost, replace_cost))
            previous = current
        return previous[-1]
