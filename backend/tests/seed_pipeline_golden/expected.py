"""Golden expectations + scoring helpers for seed_pipeline_golden samples.

Each ``EXPECTED_*`` dict declares the minimum acceptable LLM output for the
matching sample. ``score_segment_output()`` produces per-metric floats in
[0, 1] that aggregate across samples in the harness.

Why the schema is liberal:
    Real LLM outputs vary in wording. We score by:
      - membership (is canonical name X present in character_updates?)
      - alias inclusion (did 沈无双's aliases pick up 兜帽女 if applicable?)
      - relation co-existence (is there an entry connecting 林策 ↔ 沈无双?)
      - summary length range
      - hallucination check (no characters outside ``allowed_characters``)
    We do NOT require exact wording — that would over-fit to one model.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set


EXPECTED_DIALOGUE_HEAVY: Dict[str, Any] = {
    "sample_id": "DIALOGUE_HEAVY",
    "expected_characters": ["林策", "沈无双"],
    "mentioned_only_characters": ["陆君言"],
    "expected_relations": [
        {"pair": ("林策", "沈无双"), "keywords": ["盟友", "合作", "同路", "联手"]},
    ],
    "summary_length_range": (80, 500),
    "must_have_aliases": {},
    "allowed_characters": {"林策", "沈无双", "陆君言"},
    "expected_organizations": ["青衫剑派"],
}


EXPECTED_NARRATIVE_DENSE: Dict[str, Any] = {
    "sample_id": "NARRATIVE_DENSE",
    "expected_characters": ["楚轻寒", "周怀瑾"],
    "mentioned_only_characters": [],
    "expected_relations": [
        {"pair": ("楚轻寒", "周怀瑾"), "keywords": ["对立", "冲突", "试探", "暧昧", "旁观"]},
    ],
    "summary_length_range": (80, 500),
    "must_have_aliases": {},
    "allowed_characters": {"楚轻寒", "周怀瑾"},
    "expected_organizations": ["玄霜阁"],
}


EXPECTED_WORLD_BUILDING: Dict[str, Any] = {
    "sample_id": "WORLD_BUILDING",
    "expected_characters": ["萧无尘"],
    "mentioned_only_characters": [],
    "expected_relations": [],
    "summary_length_range": (80, 500),
    "must_have_aliases": {},
    "allowed_characters": {"萧无尘"},
    "expected_organizations": ["五行宗", "剑诀阁", "长老议会", "祖师堂"],
    "expected_world_rules_keywords": ["五均制", "三禁", "问心"],
}


EXPECTED_RELATIONSHIP_SHIFT: Dict[str, Any] = {
    "sample_id": "RELATIONSHIP_SHIFT",
    "expected_characters": ["裴砚一", "陆君言"],
    "mentioned_only_characters": [],
    "expected_relations": [
        {
            "pair": ("陆君言", "裴砚一"),
            "keywords": ["背叛", "操纵", "对立", "决裂", "敌对"],
        },
    ],
    "summary_length_range": (80, 500),
    "must_have_aliases": {"裴砚一": ["砚一"]},
    "allowed_characters": {"裴砚一", "陆君言", "砚一"},
    "expected_organizations": ["青衫剑派"],
}


EXPECTED_SPARSE: Dict[str, Any] = {
    "sample_id": "SPARSE",
    "expected_characters": ["姜逾白"],
    "mentioned_only_characters": ["母亲"],
    "expected_relations": [],
    "summary_length_range": (60, 400),
    "must_have_aliases": {},
    "allowed_characters": {"姜逾白", "母亲"},
    "must_not_relations_between_active": True,
}


EXPECTED_BY_ID: Dict[str, Dict[str, Any]] = {
    EXPECTED_DIALOGUE_HEAVY["sample_id"]: EXPECTED_DIALOGUE_HEAVY,
    EXPECTED_NARRATIVE_DENSE["sample_id"]: EXPECTED_NARRATIVE_DENSE,
    EXPECTED_WORLD_BUILDING["sample_id"]: EXPECTED_WORLD_BUILDING,
    EXPECTED_RELATIONSHIP_SHIFT["sample_id"]: EXPECTED_RELATIONSHIP_SHIFT,
    EXPECTED_SPARSE["sample_id"]: EXPECTED_SPARSE,
}


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _names_in_updates(character_updates: List[Dict]) -> Set[str]:
    names: Set[str] = set()
    for update in character_updates or []:
        name = (update.get("name") or "").strip()
        if name:
            names.add(name)
    return names


def _aliases_in_updates(character_updates: List[Dict]) -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {}
    for update in character_updates or []:
        name = (update.get("name") or "").strip()
        if not name:
            continue
        alias_set = {
            (a or "").strip() for a in update.get("aliases", []) if (a or "").strip()
        }
        out.setdefault(name, set()).update(alias_set)
    return out


def _relation_keys(relations: List[Dict]) -> List[Dict[str, str]]:
    """Normalise relations to {source, target, relation, evidence}."""
    out = []
    for r in relations or []:
        out.append({
            "source": (r.get("source") or "").strip(),
            "target": (r.get("target") or "").strip(),
            "relation": (r.get("relation") or "").strip(),
            "evidence": (r.get("evidence") or "").strip(),
        })
    return out


def _has_relation(relations: List[Dict[str, str]], pair: tuple, keywords: List[str]) -> bool:
    a, b = pair
    for r in relations:
        s, t = r["source"], r["target"]
        if {s, t} != {a, b}:
            continue
        haystack = f"{r['relation']} {r['evidence']}"
        if any(kw in haystack for kw in keywords):
            return True
    return False


def score_segment_output(
    output: Optional[Dict[str, Any]],
    expected: Dict[str, Any],
) -> Dict[str, float]:
    """Score one LLM segment output against its golden expectation.

    Returns a dict of metric_name -> [0, 1] float. Aggregated across samples
    by the harness.
    """
    if not isinstance(output, dict):
        return {
            "json_parse_rate": 0.0,
            "character_recall": 0.0,
            "relation_satisfied": 0.0,
            "summary_length_compliance": 0.0,
            "alias_recall": 0.0,
            "no_hallucination": 0.0,
        }

    names = _names_in_updates(output.get("character_updates", []))
    expected_chars = expected["expected_characters"]
    char_recall = (
        sum(1 for c in expected_chars if c in names) / max(1, len(expected_chars))
    )

    relations = _relation_keys(output.get("relationship_changes", []))
    expected_rels = expected.get("expected_relations", [])
    if expected_rels:
        rel_satisfied = sum(
            1 for r in expected_rels
            if _has_relation(relations, r["pair"], r["keywords"])
        ) / len(expected_rels)
    else:
        # Sparse / world-building samples: no relations expected.
        # Score 1.0 if the LLM also produced no relations between named active
        # characters; 0.0 if it hallucinated relations.
        if expected.get("must_not_relations_between_active"):
            allowed = expected["allowed_characters"]
            hallucinated = [
                r for r in relations
                if r["source"] in allowed and r["target"] in allowed
            ]
            rel_satisfied = 0.0 if hallucinated else 1.0
        else:
            rel_satisfied = 1.0

    summary = output.get("segment_summary", "") or ""
    low, high = expected["summary_length_range"]
    summary_compliance = 1.0 if low <= len(summary) <= high else 0.0

    aliases_table = _aliases_in_updates(output.get("character_updates", []))
    must_aliases = expected.get("must_have_aliases", {})
    if must_aliases:
        hits = 0
        total = 0
        for canonical, expected_aliases in must_aliases.items():
            for alias in expected_aliases:
                total += 1
                if alias in aliases_table.get(canonical, set()):
                    hits += 1
        alias_recall = hits / max(1, total)
    else:
        alias_recall = 1.0

    allowed = expected.get("allowed_characters", set())
    if allowed:
        extra = [n for n in names if n not in allowed]
        no_hallucination = 1.0 if not extra else max(0.0, 1.0 - len(extra) / 3.0)
    else:
        no_hallucination = 1.0

    return {
        "json_parse_rate": 1.0,
        "character_recall": char_recall,
        "relation_satisfied": rel_satisfied,
        "summary_length_compliance": summary_compliance,
        "alias_recall": alias_recall,
        "no_hallucination": no_hallucination,
    }


def aggregate_scores(per_sample: List[Dict[str, float]]) -> Dict[str, float]:
    """Mean of each metric across all samples."""
    if not per_sample:
        return {}
    keys = per_sample[0].keys()
    return {
        k: sum(s.get(k, 0.0) for s in per_sample) / len(per_sample)
        for k in keys
    }


def format_score_table(
    sample_ids: List[str],
    per_sample: List[Dict[str, float]],
    aggregated: Dict[str, float],
) -> str:
    """Render scores as a markdown table for stdout reporting."""
    metrics = list(per_sample[0].keys()) if per_sample else []
    header = "| sample | " + " | ".join(metrics) + " |"
    sep = "|" + "|".join(["---"] * (len(metrics) + 1)) + "|"
    rows = [header, sep]
    for sid, scores in zip(sample_ids, per_sample):
        cells = [sid] + [f"{scores.get(m, 0.0):.2f}" for m in metrics]
        rows.append("| " + " | ".join(cells) + " |")
    cells = ["**MEAN**"] + [f"**{aggregated.get(m, 0.0):.2f}**" for m in metrics]
    rows.append("| " + " | ".join(cells) + " |")
    return "\n".join(rows)
