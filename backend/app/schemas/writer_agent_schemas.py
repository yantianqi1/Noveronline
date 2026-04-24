"""Pydantic request schemas for /api/writer-agent routes."""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import Field

from ._base import AllowExtraBase


class RunWriterAgentRequest(AllowExtraBase):
    project_id: str
    task_type: str = "write_scene"


class WorldUpdateRequest(AllowExtraBase):
    project_id: str
    content: str
    chapter_order: int = 0


class ApplyReviewerRequest(AllowExtraBase):
    """Payload for ``POST /writer-agent/apply-reviewer``.

    Triggered when the user clicks "采纳改写" on the reviewer panel. The
    server re-runs :class:`WriterComposer` with the reviewer's accepted
    suggestions injected as extra constraints, then upserts the scene in
    place (same ``scene_id``) so the manuscript stays coherent.
    """

    project_id: str
    scene_id: str
    chapter_id: str = ""
    chapter_order: int = 0
    scene_order: int = 1
    preset_id: str = ""
    pov_entity_id: str = ""
    involved_entity_ids: list[str] = []
    # ``writing_brief`` is passed back from the original run so we don't need
    # to re-run the orchestrator. Accepting it raw (dict) — frontend persists
    # it from the initial ``prompt_snapshot`` / ``done`` events.
    writing_brief: dict[str, Any] = {}
    # Selected issues from the reviewer payload (frontend filters by user ticks).
    accepted_issues: list[dict[str, Any]] = []
    # Original draft — surfaced back to the composer as a rewrite source so
    # the model has concrete text to operate on.
    draft: str = ""


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


class OneClickCompleteOutlineRequest(AllowExtraBase):
    project_id: str
    chapter_id: str
    chapter_order: int = 0


class OneClickAlignWordsRequest(AllowExtraBase):
    project_id: str
    chapter_id: str
    chapter_order: int = 0
    target_word_count: int
    tolerance_pct: int = 10


class OneClickScanLexiconRequest(AllowExtraBase):
    project_id: str
    chapter_id: str
    chapter_order: int = 0
    lexicon_asset_ids: list[str] = []


class OneClickFillRelationshipsRequest(AllowExtraBase):
    project_id: str
    chapter_id: str
    chapter_order: int = 0


class OneClickContinueChapterRequest(AllowExtraBase):
    project_id: str
    chapter_id: str
    chapter_order: int = 0
    last_block_id: str = ""
    target_word_count: int = 600
    preset_id: str = ""


class UpsertForbiddenLexiconRequest(AllowExtraBase):
    project_id: str
    asset_id: str | None = None
    title: str = ""
    entries: list[Any] = []


# ---------------------------------------------------------------------
# Tool render protocol (§2 of 2026-04-19 writer-workbench plan)
#
# Tools may return a `render` payload alongside their textual `result`. The
# text is what the LLM sees; `render` is UI-only data that the frontend
# dispatches to structured cards by `type`. `data` is intentionally kept as a
# dict rather than nested Pydantic models so adding a card field doesn't
# require syncing N classes — frontend TS types are the UI contract.
# ---------------------------------------------------------------------


class ToolRenderAction(AllowExtraBase):
    """UI hint for how the user adopts a card. `endpoint` is a label for
    debugging; the frontend routes by `kind` / `type` to the appropriate
    API client function — no `fetch(endpoint)` happens on the frontend."""

    label: str
    endpoint: str = ""
    kind: str | None = None
    payload_ref: str = "data"
    confirm: str | None = None
    variant: str | None = None


class _RenderEnvelope(AllowExtraBase):
    version: int = 1
    actions: list[ToolRenderAction] = []
    tool_call_id: str | None = None


class SceneProposalRender(_RenderEnvelope):
    type: Literal["scene_proposal"] = "scene_proposal"
    data: dict


class ChapterStructureProposalRender(_RenderEnvelope):
    type: Literal["chapter_structure_proposal"] = "chapter_structure_proposal"
    data: dict


class EntityCardRender(_RenderEnvelope):
    type: Literal["entity_card"] = "entity_card"
    data: dict


class ProseDiffRender(_RenderEnvelope):
    type: Literal["prose_diff"] = "prose_diff"
    data: dict


class WordBudgetRender(_RenderEnvelope):
    type: Literal["word_budget"] = "word_budget"
    data: dict


class ThreadBoardRender(_RenderEnvelope):
    type: Literal["thread_board"] = "thread_board"
    data: dict


class RelationSubgraphRender(_RenderEnvelope):
    type: Literal["relation_subgraph"] = "relation_subgraph"
    data: dict


class SceneTimelineRender(_RenderEnvelope):
    type: Literal["scene_timeline"] = "scene_timeline"
    data: dict


class RelationshipProposalRender(_RenderEnvelope):
    type: Literal["relationship_proposal"] = "relationship_proposal"
    data: dict


ToolRenderPayload = Annotated[
    Union[
        SceneProposalRender,
        ChapterStructureProposalRender,
        EntityCardRender,
        ProseDiffRender,
        WordBudgetRender,
        ThreadBoardRender,
        RelationSubgraphRender,
        SceneTimelineRender,
        RelationshipProposalRender,
    ],
    Field(discriminator="type"),
]


class ToolExecResult(AllowExtraBase):
    """Executors' dict return shape. `result` is what the LLM sees; `render`
    is an optional UI payload surfaced via the `tool_result` SSE event."""

    result: str
    render: ToolRenderPayload | None = None
