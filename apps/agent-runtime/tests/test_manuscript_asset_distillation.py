from __future__ import annotations

from mirofish_agents.temporal.manuscript_asset_distillation import (
    MODULE_KEY,
    WINDOW_CHAR_MAX,
    WINDOW_CHAR_TARGET,
    WORKFLOW_NAME,
    build_source_windows,
    estimate_tokens,
    merge_candidates_by_identity,
    normalize_identity,
    resolve_enabled_asset_types,
    resolve_identity,
    validate_model_candidates,
    _messages,
)


def test_module_and_workflow_names() -> None:
    assert MODULE_KEY == "writer_asset_distiller"
    assert WORKFLOW_NAME == "ManuscriptAssetDistillationWorkflow"


def test_evidence_requires_exact_quote() -> None:
    sources = [
        {
            "block_id": "b1",
            "block_version": 1,
            "content_sha256": "a" * 64,
            "content_text": "林晚站在灯塔下看着大海。",
        }
    ]
    response = {
        "candidates": [
            {
                "asset_type": "character",
                "title": "林晚",
                "summary": "主角",
                "evidence": [
                    {
                        "block_id": "b1",
                        "start_offset": 0,
                        "end_offset": 2,
                        "quote": "林晚",
                    }
                ],
            },
            {
                "asset_type": "location",
                "title": "灯塔",
                "evidence": [
                    {
                        "block_id": "b1",
                        "start_offset": 0,
                        "end_offset": 2,
                        "quote": "不存在的片段",
                    }
                ],
            },
        ]
    }
    candidates = validate_model_candidates(response, sources)
    assert len(candidates) == 1
    assert candidates[0]["title"] == "林晚"
    assert candidates[0]["evidence"][0]["start_offset"] == 0


def test_quote_unique_lookup_fallback() -> None:
    sources = [
        {
            "block_id": "b1",
            "block_version": 2,
            "content_sha256": "b" * 64,
            "content_text": "夜色里的码头很安静。",
        }
    ]
    response = {
        "candidates": [
            {
                "asset_type": "location",
                "title": "码头",
                "evidence": [
                    {
                        "block_id": "b1",
                        "start_offset": 99,
                        "end_offset": 101,
                        "quote": "码头",
                    }
                ],
            }
        ]
    }
    candidates = validate_model_candidates(response, sources)
    assert len(candidates) == 1
    assert candidates[0]["evidence"][0]["start_offset"] == 4


def test_single_evidence_object_is_normalized_to_list() -> None:
    sources = [
        {
            "block_id": "b1",
            "block_version": 1,
            "content_sha256": "f" * 64,
            "content_text": "许七安持有司天监令牌。",
        }
    ]
    response = {
        "candidates": [
            {
                "asset_type": "character",
                "title": "许七安",
                "evidence": {
                    "block_id": "b1",
                    "start_offset": 0,
                    "end_offset": 3,
                    "quote": "许七安",
                },
            }
        ]
    }

    candidates = validate_model_candidates(response, sources)

    assert len(candidates) == 1
    assert candidates[0]["evidence"] == [
        {
            "block_id": "b1",
            "block_version": 1,
            "content_sha256": "f" * 64,
            "start_offset": 0,
            "end_offset": 3,
            "quote": "许七安",
        }
    ]


def test_identity_resolution_create_update_conflict() -> None:
    existing = [
        {"asset_id": "a1", "asset_type": "character", "title": "林晚", "summary": "", "lifecycle": "canon", "enabled": True},
        {"asset_id": "a2", "asset_type": "character", "title": "林晚", "summary": "", "lifecycle": "material", "enabled": True},
    ]
    create = resolve_identity({"asset_type": "location", "title": "灯塔", "identity_hints": []}, existing)
    assert create["operation"] == "create"
    update = resolve_identity({"asset_type": "character", "title": "林晚", "identity_hints": []}, existing[:1])
    assert update["operation"] == "update"
    assert update["target_asset_id"] == "a1"
    conflict = resolve_identity({"asset_type": "character", "title": "林晚", "identity_hints": []}, existing)
    assert conflict["operation"] == "conflict"
    assert "character|林晚" in normalize_identity("character", "林晚", ["Lin"])


def test_enabled_asset_types_empty_means_all_supported() -> None:
    assert resolve_enabled_asset_types([]) == sorted(
        {
            "character",
            "organization",
            "location",
            "item",
            "world_rule",
            "relationship",
            "event",
            "plot_thread",
            "terminology",
        }
    )
    assert resolve_enabled_asset_types(None) == resolve_enabled_asset_types([])
    assert resolve_enabled_asset_types(["character", "location", "bogus"]) == ["character", "location"]


def test_validate_model_candidates_filters_disabled_types() -> None:
    sources = [
        {
            "block_id": "b1",
            "block_version": 1,
            "content_sha256": "c" * 64,
            "content_text": "林晚走进了码头。",
        }
    ]
    response = {
        "candidates": [
            {
                "asset_type": "character",
                "title": "林晚",
                "evidence": [{"block_id": "b1", "start_offset": 0, "end_offset": 2, "quote": "林晚"}],
            },
            {
                "asset_type": "location",
                "title": "码头",
                "evidence": [{"block_id": "b1", "start_offset": 5, "end_offset": 7, "quote": "码头"}],
            },
        ]
    }
    only_character = validate_model_candidates(
        response, sources, enabled_asset_types=["character"]
    )
    assert [c["title"] for c in only_character] == ["林晚"]


def test_messages_include_enabled_types_only() -> None:
    sources = [
        {
            "block_id": "b1",
            "block_version": 1,
            "content_text": "正文",
            "base_offset": 0,
        }
    ]
    messages = _messages(sources, enabled_asset_types=["character", "world_rule"])
    system = messages[0]["content"]
    assert "character" in system
    assert "world_rule" in system
    assert "location" not in system or "Only extract these asset_type values: character, world_rule" in system
    assert "Only extract these asset_type values: character, world_rule" in system
    assert "evidence MUST be a JSON array" in system
    assert "summary is the asset's primary readable content" in system
    assert "canonical_name, aliases, narrative_role, appearance" in system
    assert "rule_text, scope, conditions, mechanism" in system
    assert "organization_type" not in system
    assert "Omit unknown fields" in system
    assert "same language as the manuscript" in system


def test_estimate_tokens_chars_over_four() -> None:
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 8000) == 2000


def test_build_source_windows_splits_long_chapter() -> None:
    # Force multi-window packing (~7k tokens / ~28k chars target).
    text = ("段落。" * 200 + "\n\n") * 80
    assert len(text) > WINDOW_CHAR_TARGET
    sources = [
        {
            "block_id": "b1",
            "block_version": 1,
            "content_sha256": "d" * 64,
            "content_text": text,
        }
    ]
    windows = build_source_windows(sources)
    assert len(windows) >= 2
    for window in windows:
        for unit in window:
            assert len(unit["content_text"]) <= WINDOW_CHAR_MAX
            assert unit["_full_content_text"] == text
            assert "base_offset" in unit

    # Reconstruct full text in order
    reconstructed = "".join(
        unit["content_text"] for window in windows for unit in window if unit["block_id"] == "b1"
    )
    assert reconstructed == text


def test_window_evidence_offsets_remap_to_absolute() -> None:
    full = "AAAA" + "林晚" + "BBBB"
    window_sources = [
        {
            "block_id": "b1",
            "block_version": 1,
            "content_sha256": "e" * 64,
            "content_text": "林晚" + "BBBB",
            "base_offset": 4,
            "_full_content_text": full,
        }
    ]
    response = {
        "candidates": [
            {
                "asset_type": "character",
                "title": "林晚",
                "evidence": [
                    {
                        "block_id": "b1",
                        "start_offset": 0,
                        "end_offset": 2,
                        "quote": "林晚",
                    }
                ],
            }
        ]
    }
    candidates = validate_model_candidates(
        response, window_sources, enabled_asset_types=["character"], remap_window_offsets=True
    )
    assert len(candidates) == 1
    assert candidates[0]["evidence"][0]["start_offset"] == 4
    assert candidates[0]["evidence"][0]["end_offset"] == 6
    assert full[4:6] == "林晚"


def test_merge_candidates_by_identity_unions_evidence() -> None:
    c1 = {
        "local_id": "1",
        "asset_type": "character",
        "title": "林晚",
        "summary": "短",
        "identity_hints": ["Lin"],
        "tags": ["a"],
        "payload": {"k": 1},
        "confidence": 0.5,
        "evidence": [
            {"block_id": "b1", "start_offset": 0, "end_offset": 2, "quote": "林晚"},
        ],
    }
    c2 = {
        "local_id": "2",
        "asset_type": "character",
        "title": "林晚",
        "summary": "更长的摘要内容",
        "identity_hints": ["Lin", "晚姐"],
        "tags": ["b"],
        "payload": {"k": 2, "m": 3},
        "confidence": 0.9,
        "evidence": [
            {"block_id": "b1", "start_offset": 0, "end_offset": 2, "quote": "林晚"},
            {"block_id": "b2", "start_offset": 1, "end_offset": 3, "quote": "晚姐"},
        ],
    }
    merged = merge_candidates_by_identity([c1, c2])
    assert len(merged) == 1
    m = merged[0]
    assert m["summary"] == "更长的摘要内容"
    assert m["confidence"] == 0.9
    assert set(m["identity_hints"]) == {"Lin", "晚姐"}
    assert set(m["tags"]) == {"a", "b"}
    assert m["payload"] == {"k": 2, "m": 3}
    assert len(m["evidence"]) == 2
