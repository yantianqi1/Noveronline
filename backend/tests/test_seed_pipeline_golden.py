"""Golden harness for seed-pipeline segment prompt evaluation.

Default-skipped. Run with one of:
    pytest tests/test_seed_pipeline_golden.py --run-golden
    SEED_GOLDEN=1 pytest tests/test_seed_pipeline_golden.py

Modes:
    Mock (default): uses a hand-crafted FakeGoldenLLMClient that returns
        per-sample golden output. Validates that the harness machinery + the
        scoring functions work — every metric should score 1.0.

    Real LLM (SEED_GOLDEN_REAL_LLM=1): bypasses the per-test sqlite/uploads
        sandbox (see conftest.py) and calls the user's configured LlmRouter.
        Requires a working DATABASE_URL with the ``sequential_reading`` module
        binding configured. Use this to compare prompt versions:
            git stash && SEED_GOLDEN_REAL_LLM=1 pytest ...   # baseline
            git stash pop && SEED_GOLDEN_REAL_LLM=1 pytest ... # new prompt

The harness prints a markdown table of scores at the end; capture stdout with
``-s`` to view it.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import pytest

from app.services.sequential_reader_prompts import build_segment_reading_prompt
from app.utils.llm_json import normalize_json_object

from tests.seed_pipeline_golden.samples import ALL_SAMPLES
from tests.seed_pipeline_golden.expected import (
    EXPECTED_BY_ID,
    aggregate_scores,
    format_score_table,
    score_segment_output,
)


# ---------------------------------------------------------------------------
# Mock client — returns "perfect" output per sample for harness self-test.
# ---------------------------------------------------------------------------

GOLDEN_MOCK_OUTPUTS: Dict[str, Dict[str, Any]] = {
    "DIALOGUE_HEAVY": {
        "segment_summary": (
            "[承接] 林策与沈无双夜入听风楼，秘密接头。"
            "[推进] 沈无双交出三十七人名册，确认陆君言在内，二人结为同盟，"
            "约定三个月内铲除陆君言。"
            "[悬念] 陆君言的真实身份与背后势力尚未揭开，二人能否得手仍是未知。"
        ),
        "character_updates": [
            {
                "name": "林策", "aliases": [], "status": "alive",
                "identity": "调查者", "personality_traits": ["谨慎"],
                "speech_style": "简练", "verbal_habits": [],
                "emotional_state": "凝重", "power_position": "对等",
                "goals": ["铲除陆君言"], "key_actions": ["接收名册"],
                "knowledge_gained": ["三十七人名册"], "quote_examples": ["你放心。我会保你周全。"],
                "first_seen": "seg_001",
            },
            {
                "name": "沈无双", "aliases": [], "status": "alive",
                "identity": "前青衫剑派弟子", "personality_traits": ["冷峻", "果决"],
                "speech_style": "冷静直接", "verbal_habits": [],
                "emotional_state": "戒备", "power_position": "主导",
                "goals": ["铲除陆君言"], "key_actions": ["递交名册"],
                "knowledge_gained": [], "quote_examples": ["我只需要你说话算话。"],
                "first_seen": "seg_001",
            },
        ],
        "relationship_changes": [
            {
                "source": "林策", "target": "沈无双",
                "relation": "盟友", "previous_state": "陌生",
                "trigger": "交换名册并立约",
                "evidence": "二人约定三个月内铲除陆君言。",
                "emotional_shift": "信任增长", "power_shift": "平衡",
            },
        ],
        "co_occurrence": [
            {"a": "林策", "b": "沈无双", "scene": "听风楼雅间夜会", "interaction_type": "对话"},
        ],
        "organization_dynamics": [],
        "location_state_changes": [],
        "plot_threads": [
            {"thread": "铲除陆君言", "status": "open", "detail": "三个月期限",
             "resolution_detail": ""},
        ],
        "world_building": [],
        "consistency_notes": [],
        "narrative_phase": "铺垫",
    },
    "NARRATIVE_DENSE": {
        "segment_summary": (
            "[承接] 楚轻寒受命潜入玄霜阁。"
            "[推进] 她子时翻入后院，盗取刻\"霜\"字玉牌得手；"
            "守卫周怀瑾推门搜查，看似未察觉异样转身离去。"
            "[悬念] 周怀瑾唇角的玩味笑意暗示他其实已经发现入侵者。"
        ),
        "character_updates": [
            {
                "name": "楚轻寒", "aliases": [], "status": "alive",
                "identity": "潜入者", "personality_traits": ["敏捷", "冷静"],
                "speech_style": "", "verbal_habits": [],
                "emotional_state": "高度警觉", "power_position": "暗处",
                "goals": ["盗取玉牌"], "key_actions": ["翻墙", "盗取玉牌", "撤离"],
                "knowledge_gained": ["玉牌位置"], "quote_examples": [],
                "first_seen": "seg_001",
            },
            {
                "name": "周怀瑾", "aliases": [], "status": "alive",
                "identity": "玄霜阁阁主之子", "personality_traits": ["敏锐", "城府深"],
                "speech_style": "轻笑", "verbal_habits": [],
                "emotional_state": "玩味", "power_position": "明处",
                "goals": [], "key_actions": ["持烛搜查", "佯装离开"],
                "knowledge_gained": ["可能已识破入侵者"],
                "quote_examples": ["狸猫吗？"],
                "first_seen": "seg_001",
            },
        ],
        "relationship_changes": [
            {
                "source": "楚轻寒", "target": "周怀瑾",
                "relation": "对立", "previous_state": "未知",
                "trigger": "盗窃现场被搜查",
                "evidence": "周怀瑾搜查时疑似已察觉桌下藏人。",
                "emotional_shift": "敌对", "power_shift": "下风",
            },
        ],
        "co_occurrence": [
            {"a": "楚轻寒", "b": "周怀瑾", "scene": "玄霜阁偏厅暗中相遇",
             "interaction_type": "试探"},
        ],
        "organization_dynamics": [
            {"organization": "玄霜阁", "event": "玉牌被盗，周怀瑾在场未声张",
             "members_involved": ["周怀瑾"]},
        ],
        "location_state_changes": [
            {"location": "玄霜阁偏厅", "change": "玉牌被盗"},
        ],
        "plot_threads": [
            {"thread": "刻霜玉牌", "status": "progressed",
             "detail": "玉牌被楚轻寒取走", "resolution_detail": ""},
        ],
        "world_building": [],
        "consistency_notes": [],
        "narrative_phase": "升级",
    },
    "WORLD_BUILDING": {
        "segment_summary": (
            "[承接] 介绍五行宗的历史与制度根基。"
            "[推进] 五行宗八百年传承靠\"五均制\"——五脉分立、宗主有限统帅；"
            "弟子需经\"问心\"入门，宗内三禁皆死罪，由独立的剑诀阁清门使执行；"
            "现任宗主萧无尘为第十二任。"
            "[悬念] 五均制能否在剧情冲突中维持，剑诀阁的实际权力如何运作。"
        ),
        "character_updates": [
            {
                "name": "萧无尘", "aliases": [], "status": "alive",
                "identity": "五行宗第十二任宗主", "personality_traits": [],
                "speech_style": "", "verbal_habits": [],
                "emotional_state": "", "power_position": "宗主",
                "goals": [], "key_actions": [], "knowledge_gained": [],
                "quote_examples": [], "first_seen": "seg_001",
            },
        ],
        "relationship_changes": [],
        "co_occurrence": [],
        "organization_dynamics": [
            {"organization": "五行宗", "event": "介绍五均制与三禁",
             "members_involved": ["萧无尘"]},
            {"organization": "剑诀阁", "event": "清门使执行三禁死罪",
             "members_involved": []},
        ],
        "location_state_changes": [],
        "plot_threads": [],
        "world_building": [
            {"fact": "五行宗采用五均制：五脉分立，宗主无权干涉各脉内务",
             "evidence": "开宗祖师所定"},
            {"fact": "宗内三禁：欺师、叛宗、私传五行心法皆死罪",
             "evidence": "三百年来违禁者四十六人皆被处死"},
            {"fact": "剑诀阁不属五脉，直接听命于祖师堂",
             "evidence": "清门使由剑诀阁派出"},
            {"fact": "弟子入门须经问心考验：三日三夜不眠不食于祖师堂静坐",
             "evidence": "问心考验"},
        ],
        "consistency_notes": [],
        "narrative_phase": "铺垫",
    },
    "RELATIONSHIP_SHIFT": {
        "segment_summary": (
            "[承接] 裴砚一三年前因匿名密信指控青衫剑派而与师父决裂。"
            "[推进] 镜湖夜会，陆君言坦承所有密信均出自他手，"
            "三年的追查、愤怒、决裂全是师兄陆君言的布局。"
            "[悬念] 裴砚一握剑颤抖，他是会反抗还是接受成为陆君言的工具。"
        ),
        "character_updates": [
            {
                "name": "裴砚一", "aliases": ["砚一"], "status": "alive",
                "identity": "陆君言师弟", "personality_traits": ["执着", "易怒"],
                "speech_style": "急切", "verbal_habits": [],
                "emotional_state": "震惊崩溃", "power_position": "受控",
                "goals": ["原本：复仇青衫剑派"], "key_actions": ["拔剑"],
                "knowledge_gained": ["陆君言才是幕后操纵者"],
                "quote_examples": ["你为什么……"],
                "first_seen": "seg_003",
            },
            {
                "name": "陆君言", "aliases": [], "status": "alive",
                "identity": "裴砚一师兄/真凶", "personality_traits": ["阴险", "温文掩饰"],
                "speech_style": "温和却冷", "verbal_habits": [],
                "emotional_state": "胜券在握", "power_position": "主导",
                "goals": ["把裴砚一变成自己的剑"], "key_actions": ["揭示真相"],
                "knowledge_gained": [],
                "quote_examples": ["从今夜起，你只能是我的人。"],
                "first_seen": "seg_003",
            },
        ],
        "relationship_changes": [
            {
                "source": "陆君言", "target": "裴砚一",
                "relation": "操纵/背叛", "previous_state": "师兄弟",
                "trigger": "陆君言坦承三年布局",
                "evidence": "陆君言：那封密信是我亲笔写的。",
                "emotional_shift": "信任破裂", "power_shift": "上风",
            },
        ],
        "co_occurrence": [
            {"a": "裴砚一", "b": "陆君言", "scene": "镜湖月下对峙",
             "interaction_type": "对话"},
        ],
        "organization_dynamics": [],
        "location_state_changes": [
            {"location": "镜湖", "change": "成为关系破裂之地"},
        ],
        "plot_threads": [
            {"thread": "三年阴谋", "status": "resolved",
             "detail": "陆君言才是真凶",
             "resolution_detail": "陆君言坦承伪造青衫剑派密信"},
            {"thread": "裴砚一的归属", "status": "open",
             "detail": "成为陆君言之剑还是反抗", "resolution_detail": ""},
        ],
        "world_building": [],
        "consistency_notes": [],
        "narrative_phase": "转折",
    },
    "SPARSE": {
        "segment_summary": (
            "[承接] 姜逾白十年后回到故乡客栈。"
            "[推进] 雨夜独坐，回忆母亲临终遗言\"无论如何不要回去\"，"
            "却仍违背遗愿归来；将冷茶倒掉重沏一壶最浓的。"
            "[悬念] 他违背遗愿归来的原因，以及这座城等待他的是什么。"
        ),
        "character_updates": [
            {
                "name": "姜逾白", "aliases": [], "status": "alive",
                "identity": "归乡者", "personality_traits": ["执拗", "沉郁"],
                "speech_style": "", "verbal_habits": [],
                "emotional_state": "苍凉", "power_position": "孤身",
                "goals": ["重新面对故乡"], "key_actions": ["独坐", "重沏浓茶"],
                "knowledge_gained": [], "quote_examples": [],
                "first_seen": "seg_001",
            },
        ],
        "relationship_changes": [],
        "co_occurrence": [],
        "organization_dynamics": [],
        "location_state_changes": [
            {"location": "城西客栈", "change": "雨已下三日"},
        ],
        "plot_threads": [
            {"thread": "姜逾白归乡之因", "status": "open",
             "detail": "违背母亲遗言归来", "resolution_detail": ""},
        ],
        "world_building": [],
        "consistency_notes": [],
        "narrative_phase": "铺垫",
    },
}


class FakeGoldenLLMClient:
    """Returns the canned golden output for whichever sample text it sees."""

    def chat_json_value(self, messages, temperature=0.3, max_tokens=8192):
        user_content = ""
        for msg in messages:
            if msg.get("role") == "user":
                user_content = msg.get("content", "")
                break
        for sample_id, payload in GOLDEN_MOCK_OUTPUTS.items():
            from tests.seed_pipeline_golden.samples import SAMPLES_BY_ID
            sample_text = SAMPLES_BY_ID[sample_id]["text"]
            # Match by a stable substring (chapter heading).
            heading = sample_text.split("\n")[0]
            if heading and heading in user_content:
                return dict(payload)
        raise AssertionError(
            f"FakeGoldenLLMClient could not match any sample in user content: "
            f"{user_content[:200]!r}"
        )


def _build_real_llm_client():
    """Construct a real LlmRouter client; only call in real-LLM mode."""
    from app.services.llm_router import LlmRouter
    from app.services.sequential_reader import MODULE_KEY
    return LlmRouter().build_client(MODULE_KEY)


# ---------------------------------------------------------------------------
# The harness test
# ---------------------------------------------------------------------------

@pytest.mark.golden
def test_segment_prompt_golden_harness():
    """Score the segment prompt against the 5 golden samples.

    Mock mode (default): expects every metric == 1.0 — verifies the harness.
    Real-LLM mode: prints scores; compare across prompt versions manually.
    """
    use_real = os.environ.get("SEED_GOLDEN_REAL_LLM") == "1"
    client = _build_real_llm_client() if use_real else FakeGoldenLLMClient()

    sample_ids: List[str] = []
    per_sample_scores: List[Dict[str, float]] = []
    raw_outputs: List[Dict[str, Any]] = []

    for sample in ALL_SAMPLES:
        sample_id = sample["id"]
        expected = EXPECTED_BY_ID[sample_id]
        messages = build_segment_reading_prompt(sample["context"], sample["text"])
        try:
            raw = client.chat_json_value(messages, temperature=0.3, max_tokens=8192)
            output = normalize_json_object(raw, f"golden:{sample_id}")
        except Exception as exc:  # noqa: BLE001 — we want to record any failure mode
            output = None
            print(f"\n[{sample_id}] LLM call/parse failed: {type(exc).__name__}: {exc}")

        scores = score_segment_output(output, expected)
        sample_ids.append(sample_id)
        per_sample_scores.append(scores)
        raw_outputs.append(output if output is not None else {})

    aggregated = aggregate_scores(per_sample_scores)
    table = format_score_table(sample_ids, per_sample_scores, aggregated)

    # Print to stdout (use -s to view live).
    print("\n=== Segment Prompt Golden Scores ===")
    print(table)
    print(f"\nMode: {'REAL_LLM' if use_real else 'MOCK'}")

    if use_real:
        # Real-LLM mode just reports — the user is comparing across versions.
        # Soft floor: at least JSON parsed for every sample.
        assert aggregated.get("json_parse_rate", 0.0) >= 0.8, (
            f"Real-LLM JSON parse rate too low: {aggregated.get('json_parse_rate')}"
        )
    else:
        # Mock mode must score perfectly — otherwise the scoring logic is broken.
        for sid, scores in zip(sample_ids, per_sample_scores):
            for metric, value in scores.items():
                assert value == 1.0, (
                    f"Mock mode metric {metric} scored {value} on sample {sid}; "
                    f"output: {json.dumps(raw_outputs[sample_ids.index(sid)], ensure_ascii=False)[:300]}"
                )
