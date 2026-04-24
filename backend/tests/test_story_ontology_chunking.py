"""Phase E-5 — story_ontology_generator chunk + merge unit tests."""

from __future__ import annotations

from typing import Any, Dict, List

from app.services.story_ontology_generator import StoryOntologyGenerator


def test_chunk_source_returns_single_chunk_when_under_cap():
    chunks = StoryOntologyGenerator._chunk_source("hello world", chunk_size=1024)
    assert chunks == ["hello world"]


def test_chunk_source_splits_at_paragraph_boundaries():
    para_a = "A" * 30
    para_b = "B" * 30
    para_c = "C" * 30
    text = "\n\n".join([para_a, para_b, para_c])
    chunks = StoryOntologyGenerator._chunk_source(text, chunk_size=70)
    # Each paragraph fits but combined exceed 70 → split happens at boundary
    assert len(chunks) >= 2
    rejoined = "".join(chunks)
    # No content lost
    assert para_a in rejoined and para_b in rejoined and para_c in rejoined


def test_chunk_source_keeps_oversized_paragraph_intact():
    """If a single paragraph already exceeds chunk_size, don't split mid-paragraph."""
    huge = "X" * 200
    chunks = StoryOntologyGenerator._chunk_source(huge, chunk_size=50)
    assert len(chunks) == 1
    assert chunks[0] == huge


def test_merge_ontology_payloads_dedupes_entities_and_accumulates_examples():
    payloads: List[Dict[str, Any]] = [
        {
            "entity_types": [
                {
                    "name": "Character",
                    "description": "first description",
                    "attributes": [
                        {"name": "level", "type": "number", "description": "战力"},
                    ],
                    "examples": ["沈渊", "柳如烟"],
                },
            ],
            "edge_types": [
                {
                    "name": "ALLEGIANCE",
                    "description": "效忠关系",
                    "source_targets": [{"source": "Character", "target": "Organization"}],
                    "attributes": [],
                },
            ],
            "analysis_summary": "first",
            "story_focus": ["focus_a", "focus_b"],
        },
        {
            "entity_types": [
                {
                    "name": "Character",
                    "description": "second description",  # ignored: first wins
                    "attributes": [
                        {"name": "level", "type": "number", "description": "战力"},  # dedup
                        {"name": "secret", "type": "text", "description": "秘密"},  # new
                    ],
                    "examples": ["沈渊", "暗影主"],  # 沈渊 dedupe, 暗影主 added
                },
                {
                    "name": "Faction",
                    "description": "势力",
                    "attributes": [],
                    "examples": ["正道"],
                },
            ],
            "edge_types": [
                {
                    "name": "ALLEGIANCE",
                    "description": "",
                    "source_targets": [
                        {"source": "Character", "target": "Faction"},  # new pair
                    ],
                    "attributes": [{"name": "since", "type": "text", "description": "起始"}],
                },
            ],
            "analysis_summary": "second summary that is much longer than the first one",
            "story_focus": ["focus_a", "focus_c"],
        },
    ]

    merged = StoryOntologyGenerator._merge_ontology_payloads(payloads)

    # Entities deduped by name
    char_names = [e["name"] for e in merged["entity_types"]]
    assert char_names.count("Character") == 1
    assert "Faction" in char_names
    char = next(e for e in merged["entity_types"] if e["name"] == "Character")
    # First non-empty description wins
    assert char["description"] == "first description"
    # Attributes deduped by name, both kept
    attr_names = [a["name"] for a in char["attributes"]]
    assert attr_names == ["level", "secret"]
    # Examples accumulated and deduped (Character has 沈渊, 柳如烟, 暗影主)
    assert set(char["examples"]) == {"沈渊", "柳如烟", "暗影主"}

    # Edges deduped by name, source_targets merged
    allegiance = next(e for e in merged["edge_types"] if e["name"] == "ALLEGIANCE")
    pairs = [(st["source"], st["target"]) for st in allegiance["source_targets"]]
    assert ("Character", "Organization") in pairs
    assert ("Character", "Faction") in pairs

    # analysis_summary: longest wins
    assert merged["analysis_summary"].startswith("second summary")

    # story_focus: deduped in order
    assert merged["story_focus"] == ["focus_a", "focus_b", "focus_c"]


def test_merge_examples_capped_at_ten():
    payloads = [
        {
            "entity_types": [
                {
                    "name": "Character",
                    "examples": [f"角色{i}" for i in range(8)],
                },
            ],
        },
        {
            "entity_types": [
                {
                    "name": "Character",
                    "examples": [f"角色{i}" for i in range(10, 20)],
                },
            ],
        },
    ]
    merged = StoryOntologyGenerator._merge_ontology_payloads(payloads)
    char = next(e for e in merged["entity_types"] if e["name"] == "Character")
    assert len(char["examples"]) == 10
