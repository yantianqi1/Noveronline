"""Agent 分级模板注册表。"""

from __future__ import annotations

import copy
from typing import Dict, List


TEMPLATE_VERSION = "v1"
DEFAULT_TIER = "supporting"

TIER_ORDER = {
    "minor": 0,
    "supporting": 1,
    "major": 2,
    "protagonist": 3,
}

COMMON_SECTIONS = {
    "protagonist": ["identity", "motivation", "tension", "relationship", "behavior", "state", "risk", "private"],
    "major": ["identity", "motivation", "tension", "relationship", "behavior", "state", "risk", "private"],
    "supporting": ["identity", "motivation", "tension", "relationship", "state"],
    "minor": ["identity", "state", "summary"],
}

TYPE_FIELDS = {
    "character": [
        "identity_hint",
        "personality",
        "skills",
        "loyalty",
        "secrets",
        "recent_turning_points",
        "long_term_goal",
        "short_term_goal",
    ],
    "organization": [
        "organization_type",
        "resources",
        "internal_factions",
        "territorial_control",
        "public_stance",
        "strategic_goal",
        "conflict_targets",
    ],
    "relationship": [
        "history",
        "power_dynamic",
        "trust_level",
        "conflict_trigger",
        "stability_forecast",
        "last_action",
    ],
    "generic": [],
}


class AgentTemplateRegistry:
    """集中管理 agent_kind 与 importance_tier 的模板定义。"""

    def normalize_tier(self, importance_tier: str) -> str:
        tier = str(importance_tier or "").strip().lower()
        return tier if tier in COMMON_SECTIONS else DEFAULT_TIER

    def normalize_kind(self, agent_kind: str) -> str:
        kind = str(agent_kind or "").strip().lower()
        return kind if kind in TYPE_FIELDS else "generic"

    def describe(self, agent_kind: str, importance_tier: str) -> Dict[str, object]:
        kind = self.normalize_kind(agent_kind)
        tier = self.normalize_tier(importance_tier)
        return {
            "agent_kind": kind,
            "importance_tier": tier,
            "template_key": f"{kind}.{tier}.{TEMPLATE_VERSION}",
            "template_version": TEMPLATE_VERSION,
            "template_sections": copy.deepcopy(COMMON_SECTIONS[tier]),
            "type_fields": copy.deepcopy(TYPE_FIELDS[kind]),
        }

    def compare_tiers(self, left: str, right: str) -> int:
        return TIER_ORDER[self.normalize_tier(left)] - TIER_ORDER[self.normalize_tier(right)]

    def max_tier(self, tiers: List[str]) -> str:
        filtered = [self.normalize_tier(item) for item in tiers if str(item or "").strip()]
        if not filtered:
            return DEFAULT_TIER
        return max(filtered, key=lambda item: TIER_ORDER[item])
