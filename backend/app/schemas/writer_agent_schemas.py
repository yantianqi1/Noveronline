"""Pydantic request schemas for /api/writer-agent routes."""

from __future__ import annotations

from typing import Any

from ._base import AllowExtraBase


class RunWriterAgentRequest(AllowExtraBase):
    project_id: str
    task_type: str = "write_scene"


class WorldUpdateRequest(AllowExtraBase):
    project_id: str
    content: str
    chapter_order: int = 0


class UpdateSceneRequest(AllowExtraBase):
    project_id: str = ""
    content: str | None = None
    title: str | None = None


class ReorderScenesRequest(AllowExtraBase):
    project_id: str = ""
    scene_ids: list[str] = []


class CompileChapterRequest(AllowExtraBase):
    project_id: str = ""


class CreatePresetRequest(AllowExtraBase):
    name: str
    system_prompt: str
    project_id: str | None = None
    description: str = ""
    is_default: int = 0


class UpdatePresetRequest(AllowExtraBase):
    project_id: str = ""
    name: str | None = None
    system_prompt: str | None = None
    description: str | None = None
    is_default: int | None = None


class CreateChapterRequest(AllowExtraBase):
    title: str = ""
    chapter_order: int | None = None


class UpdateChapterRequest(AllowExtraBase):
    project_id: str = ""
    title: str | None = None
    summary: str | None = None
    outline_json: str | None = None
    timeline_note: str | None = None
    open_threads_json: str | None = None
    pov_character: str | None = None
    outline_label: str | None = None


class RestoreOutlineVersionRequest(AllowExtraBase):
    project_id: str = ""


class ManuscriptCommitRequest(AllowExtraBase):
    content: str
    source_scene_id: str | None = None
    insert_after_block_id: str | None = None
    chapter_id: str | None = None
    chapter_tag: str | None = None
    pov_entity_id: str | None = None
    location: str | None = None
    involved_entities_json: str | None = None


class UpdateBlockRequest(AllowExtraBase):
    project_id: str = ""
    content: str | None = None
    chapter_id: str | None = None
    chapter_tag: str | None = None


class ReorderManuscriptRequest(AllowExtraBase):
    block_ids: list[str] = []


class TagBlocksRequest(AllowExtraBase):
    block_ids: list[str] = []
    chapter_tag: str = ""


class MoveBlockRequest(AllowExtraBase):
    project_id: str = ""
    chapter_id: str | None = None


# ---------------------------------------------------------------------
# Book-run (multi-chapter agent task)
# ---------------------------------------------------------------------


class CreateBookPlanRequest(AllowExtraBase):
    project_id: str
    title: str
    chapter_count: int
    per_chapter_word_target: int
    word_tolerance_pct: int = 10
    overall_direction: str = ""
    global_brief: str = ""
    start_chapter_order: int = 1
    forbidden_lexicon_asset_ids: list[str] = []
    style_asset_ids: list[str] = []
    preset_id: str | None = None


class UpdateBookPlanRequest(AllowExtraBase):
    title: str | None = None
    chapter_count: int | None = None
    per_chapter_word_target: int | None = None
    word_tolerance_pct: int | None = None
    overall_direction: str | None = None
    global_brief: str | None = None
    start_chapter_order: int | None = None
    forbidden_lexicon_asset_ids: list[str] | None = None
    style_asset_ids: list[str] | None = None
    preset_id: str | None = None
    status: str | None = None


class RunBookRunRequest(AllowExtraBase):
    plan_id: str


class UpsertForbiddenLexiconRequest(AllowExtraBase):
    project_id: str
    asset_id: str | None = None
    title: str = ""
    entries: list[Any] = []
