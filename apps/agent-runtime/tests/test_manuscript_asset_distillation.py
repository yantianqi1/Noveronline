from __future__ import annotations

from mirofish_agents.temporal.manuscript_asset_distillation import (
    MODULE_KEY,
    WORKFLOW_NAME,
    normalize_identity,
    resolve_identity,
    validate_model_candidates,
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
