"""Native FastAPI writer-agent routes."""

from __future__ import annotations

import json
import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, StreamingResponse

from .common import err, ok
from app.schemas.writer_agent_schemas import (
    CompileChapterRequest,
    CreateBookPlanRequest,
    CreateChapterRequest,
    CreatePresetRequest,
    ManuscriptCommitRequest,
    MoveBlockRequest,
    ReorderManuscriptRequest,
    ReorderScenesRequest,
    RestoreOutlineVersionRequest,
    RunBookRunRequest,
    RunWriterAgentRequest,
    TagBlocksRequest,
    UpdateBlockRequest,
    UpdateBookPlanRequest,
    UpdateChapterRequest,
    UpdatePresetRequest,
    UpdateSceneRequest,
    UpsertForbiddenLexiconRequest,
    WorldUpdateRequest,
)

router = APIRouter(prefix="/writer-agent", tags=["writer-agent"])
ALLOWED_TASK_TYPES = {"write_scene", "continue", "outline"}


def sse_response(generator):
    return StreamingResponse(generator, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@router.post("/run")
async def run_writer_agent(body: RunWriterAgentRequest):
    payload = body.model_dump()
    if not payload.get("project_id"):
        return err("缺少 project_id", status_code=400)
    task_type = payload.get("task_type", "write_scene")
    if task_type not in ALLOWED_TASK_TYPES:
        return err(f"不支持的 task_type: {task_type}，支持: {', '.join(sorted(ALLOWED_TASK_TYPES))}", status_code=400)
    from app.services.writer_agent.orchestrator import WriterOrchestrator
    orchestrator = WriterOrchestrator()

    async def events():
        try:
            async for event in orchestrator.run(payload):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return sse_response(events())


@router.post("/world-update")
async def run_world_update(body: WorldUpdateRequest):
    payload = body.model_dump()
    project_id = payload.get("project_id")
    content = (payload.get("content") or "").strip()
    if not project_id or not content:
        return err("缺少 project_id 或 content", status_code=400)
    from app.services.llm_router import LlmRouter
    from app.services.writer_agent.agent_loop import AgentLoop
    from app.services.writer_agent.prompts import build_world_update_prompt
    from app.services.writer_agent.tools import NOVEL_TOOLS
    chapter_order = _int(payload.get("chapter_order"), 0)
    router = LlmRouter()
    client = await router.build_async_client("writer_orchestrator")
    loop = AgentLoop(client, NOVEL_TOOLS, build_world_update_prompt(project_id, chapter_order), project_id, time.monotonic())
    user_msg = f"以下是作者刚确认采用的散文（第{chapter_order}章）：\n\n{content}"

    async def events():
        try:
            async for event in loop.run(user_msg):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return sse_response(events())


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@router.get("/scenes/{chapter_id}")
async def list_scenes(chapter_id: str, project_id: str = ""):
    from app.services.writer_agent.scene_service import SceneService
    return ok(SceneService().list_scenes(project_id, chapter_id))


@router.get("/scenes/detail/{scene_id}")
async def get_scene_detail(scene_id: str, project_id: str = ""):
    from app.services.writer_agent.scene_service import SceneService
    return ok(SceneService().get_scene(project_id, scene_id))


@router.put("/scenes/{scene_id}")
async def update_scene(scene_id: str, body: UpdateSceneRequest):
    payload = body.model_dump(exclude_unset=True)
    from app.services.writer_agent.scene_service import SceneService
    return ok(SceneService().update_scene(payload.get("project_id", ""), scene_id, content=payload.get("content"), title=payload.get("title")))


@router.delete("/scenes/{scene_id}")
async def delete_scene(scene_id: str, project_id: str = ""):
    from app.services.writer_agent.scene_service import SceneService
    SceneService().delete_scene(project_id, scene_id)
    return ok(None)


@router.post("/scenes/{chapter_id}/reorder")
async def reorder_scenes(chapter_id: str, body: ReorderScenesRequest):
    payload = body.model_dump()
    from app.services.writer_agent.scene_service import SceneService
    SceneService().reorder_scenes(payload.get("project_id", ""), chapter_id, payload.get("scene_ids", []))
    return ok(None)


@router.post("/scenes/{chapter_id}/compile")
async def compile_chapter_from_scenes(chapter_id: str, body: CompileChapterRequest):
    payload = body.model_dump()
    from app.services.writer_agent.scene_service import SceneService
    return ok(SceneService().compile_chapter(payload.get("project_id", ""), chapter_id))


@router.get("/presets")
async def list_presets(project_id: str = ""):
    from app.services.writer_agent.preset_service import PresetService
    return ok(PresetService().list_presets(project_id))


@router.post("/presets")
async def create_preset(body: CreatePresetRequest):
    payload = body.model_dump()
    from app.services.writer_agent.preset_service import PresetService
    return ok(PresetService().create_preset(payload.get("project_id"), payload["name"], payload["system_prompt"], payload.get("description", ""), payload.get("is_default", 0)))


@router.put("/presets/{preset_id}")
async def update_preset(preset_id: str, body: UpdatePresetRequest):
    payload = body.model_dump(exclude_unset=True)
    from app.services.writer_agent.preset_service import PresetService
    return ok(PresetService().update_preset(payload.get("project_id", ""), preset_id, **{k: v for k, v in payload.items() if k in ("name", "system_prompt", "description", "is_default")}))


@router.delete("/presets/{preset_id}")
async def delete_preset(preset_id: str, project_id: str = ""):
    from app.services.writer_agent.preset_service import PresetService
    PresetService().delete_preset(project_id, preset_id)
    return ok(None)


@router.get("/chapters/{project_id}")
async def list_chapters(project_id: str):
    from app.services.writer_agent.chapter_service import ChapterService
    return ok(ChapterService().list_chapters(project_id))


@router.post("/chapters/{project_id}")
async def create_chapter(project_id: str, body: CreateChapterRequest):
    payload = body.model_dump()
    from app.services.writer_agent.chapter_service import ChapterService
    return ok(ChapterService().create_chapter(project_id, title=payload.get("title", ""), chapter_order=payload.get("chapter_order")))


@router.put("/chapters/detail/{chapter_id}")
async def update_chapter(chapter_id: str, body: UpdateChapterRequest):
    payload = body.model_dump(exclude_unset=True)
    from app.services.writer_agent.chapter_service import ChapterService
    fields = {k: v for k, v in payload.items() if k in ("title", "summary", "outline_json", "timeline_note", "open_threads_json", "pov_character", "outline_label")}
    return ok(ChapterService().update_chapter(payload.get("project_id", ""), chapter_id, **fields))


@router.get("/chapters/detail/{chapter_id}/outline-versions")
async def list_outline_versions(chapter_id: str, project_id: str = ""):
    from app.services.writer_agent.chapter_service import ChapterService
    return ok(ChapterService().list_outline_versions(project_id, chapter_id))


@router.get("/chapters/detail/{chapter_id}/outline-versions/{version_id}")
async def get_outline_version(chapter_id: str, version_id: str, project_id: str = ""):
    from app.services.writer_agent.chapter_service import ChapterService
    version = ChapterService().db.get_outline_version(project_id, version_id)
    return ok(version) if version else err("版本不存在", status_code=404)


@router.post("/chapters/detail/{chapter_id}/outline-versions/{version_id}/restore")
async def restore_outline_version(chapter_id: str, version_id: str, body: RestoreOutlineVersionRequest):
    payload = body.model_dump()
    from app.services.writer_agent.chapter_service import ChapterService
    return ok(ChapterService().restore_outline_version(payload.get("project_id", ""), chapter_id, version_id))


@router.delete("/chapters/detail/{chapter_id}")
async def delete_chapter(chapter_id: str, project_id: str = ""):
    from app.services.writer_agent.chapter_service import ChapterService
    ChapterService().delete_chapter(project_id, chapter_id)
    return ok(None)


@router.post("/manuscript/{project_id}/commit")
async def commit_to_manuscript(project_id: str, body: ManuscriptCommitRequest):
    payload = body.model_dump()
    content = payload.get("content", "")
    if not content.strip():
        return err("内容不能为空", status_code=400)
    from app.services.writer_agent.manuscript_service import ManuscriptService
    return ok(await ManuscriptService().commit(project_id, content=content, source_scene_id=payload.get("source_scene_id"), insert_after_block_id=payload.get("insert_after_block_id"), chapter_id=payload.get("chapter_id"), chapter_tag=payload.get("chapter_tag"), pov_entity_id=payload.get("pov_entity_id"), location=payload.get("location"), involved_entities_json=payload.get("involved_entities_json")))


@router.get("/manuscript/{project_id}")
async def list_manuscript(project_id: str, include_content: bool = True, chapter_id: str | None = None):
    from app.services.writer_agent.manuscript_service import ManuscriptService
    return ok(ManuscriptService().list_blocks(project_id, include_content, chapter_id=chapter_id))


@router.put("/manuscript/block/{block_id}")
async def update_manuscript_block(block_id: str, body: UpdateBlockRequest):
    payload = body.model_dump(exclude_unset=True)
    from app.services.writer_agent.manuscript_service import ManuscriptService
    fields = {k: v for k, v in payload.items() if k in ("content", "chapter_id", "chapter_tag")}
    return ok(ManuscriptService().update_block(payload.get("project_id", ""), block_id, **fields))


@router.delete("/manuscript/block/{block_id}")
async def delete_manuscript_block(block_id: str, project_id: str = ""):
    from app.services.writer_agent.manuscript_service import ManuscriptService
    ManuscriptService().delete_block(project_id, block_id)
    return ok(None)


@router.put("/manuscript/{project_id}/reorder")
async def reorder_manuscript(project_id: str, body: ReorderManuscriptRequest):
    payload = body.model_dump()
    from app.services.writer_agent.manuscript_service import ManuscriptService
    ManuscriptService().reorder(project_id, payload.get("block_ids", []))
    return ok(None)


@router.put("/manuscript/{project_id}/tag")
async def tag_manuscript_blocks(project_id: str, body: TagBlocksRequest):
    payload = body.model_dump()
    from app.services.writer_agent.manuscript_service import ManuscriptService
    return ok({"updated_count": ManuscriptService().tag_blocks(project_id, payload.get("block_ids", []), payload.get("chapter_tag", ""))})


@router.put("/manuscript/block/{block_id}/move")
async def move_manuscript_block(block_id: str, body: MoveBlockRequest):
    payload = body.model_dump(exclude_unset=True)
    from app.services.writer_agent.manuscript_service import ManuscriptService
    return ok(ManuscriptService().move_block(payload.get("project_id", ""), block_id, payload.get("chapter_id")))


@router.get("/manuscript/{project_id}/export")
async def export_manuscript(project_id: str, format: str = "txt"):
    from app.services.writer_agent.manuscript_service import ManuscriptService
    return PlainTextResponse(ManuscriptService().export_text(project_id, format), media_type="text/plain; charset=utf-8", headers={"Content-Disposition": f"attachment; filename=manuscript.{format}"})


@router.get("/manuscript/{project_id}/continuation-context")
async def get_continuation_context(project_id: str, token_budget: int = 8000, last_block_id: str | None = None):
    from app.services.writer_agent.manuscript_context_builder import build_continuation_context
    return ok(build_continuation_context(project_id, token_budget, last_block_id=last_block_id))


@router.post("/migrate/{project_id}")
async def migrate_project(project_id: str):
    del project_id
    return err(
        "legacy novel.sqlite3 回填接口已废弃；请改用统一数据库迁移脚本与 verify_project_migration 校验工具。",
        status_code=410,
        debug=False,
    )


# ---------------------------------------------------------------------
# Book-run: multi-chapter agent task
# ---------------------------------------------------------------------


@router.get("/book-plans")
async def list_book_plans(project_id: str = ""):
    if not project_id:
        return err("缺少 project_id", status_code=400)
    from app.services.writer_agent.book_plan_service import BookPlanService
    return ok(BookPlanService().list_plans(project_id))


@router.post("/book-plans")
async def create_book_plan(body: CreateBookPlanRequest):
    payload = body.model_dump()
    from app.services.writer_agent.book_plan_service import BookPlanService
    svc = BookPlanService()
    plan = svc.create_plan(
        project_id=payload["project_id"],
        title=payload["title"],
        chapter_count=payload["chapter_count"],
        per_chapter_word_target=payload["per_chapter_word_target"],
        word_tolerance_pct=payload.get("word_tolerance_pct", 10),
        overall_direction=payload.get("overall_direction", ""),
        global_brief=payload.get("global_brief", ""),
        start_chapter_order=payload.get("start_chapter_order", 1),
        forbidden_lexicon_asset_ids=payload.get("forbidden_lexicon_asset_ids") or [],
        style_asset_ids=payload.get("style_asset_ids") or [],
        preset_id=payload.get("preset_id"),
    )
    return ok(plan)


@router.get("/book-plans/{plan_id}")
async def get_book_plan(plan_id: str):
    from app.services.writer_agent.book_plan_service import BookPlanService
    plan = BookPlanService().get_plan(plan_id)
    return ok(plan) if plan else err("book_plan 不存在", status_code=404)


@router.put("/book-plans/{plan_id}")
async def update_book_plan(plan_id: str, body: UpdateBookPlanRequest):
    payload = body.model_dump(exclude_unset=True)
    from app.services.writer_agent.book_plan_service import BookPlanService
    plan = BookPlanService().update_plan(plan_id, **payload)
    return ok(plan) if plan else err("book_plan 不存在", status_code=404)


@router.delete("/book-plans/{plan_id}")
async def delete_book_plan(plan_id: str):
    from app.services.writer_agent.book_plan_service import BookPlanService
    BookPlanService().delete_plan(plan_id)
    return ok(None)


@router.post("/book-run")
async def run_book_run(body: RunBookRunRequest):
    payload = body.model_dump()
    plan_id = payload.get("plan_id")
    if not plan_id:
        return err("缺少 plan_id", status_code=400)
    from app.services.writer_agent.book_run_orchestrator import BookRunOrchestrator
    orchestrator = BookRunOrchestrator()

    async def events():
        try:
            async for event in orchestrator.run(plan_id):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return sse_response(events())


@router.post("/book-run/abort")
async def abort_book_run(body: RunBookRunRequest):
    """Abort by flipping plan.status to 'aborted'.

    The orchestrator is non-cooperative for now; status change lets UI surface
    intent and future in-flight loops can watch this flag.
    """
    payload = body.model_dump()
    plan_id = payload.get("plan_id")
    if not plan_id:
        return err("缺少 plan_id", status_code=400)
    from app.services.writer_agent.book_plan_service import BookPlanService
    svc = BookPlanService()
    svc.set_status(plan_id, "aborted", last_stage="ABORTED")
    return ok({"plan_id": plan_id, "status": "aborted"})


@router.get("/forbidden-lexicons")
async def list_forbidden_lexicons(project_id: str = "", include_entries: bool = False):
    if not project_id:
        return err("缺少 project_id", status_code=400)
    from app.services.assets.assets_service import AssetsService
    svc = AssetsService()
    rows = svc.list_merged(
        project_id=project_id,
        asset_type="forbidden_lexicon",
        enabled_only=False,
        limit=50,
    )
    if not include_entries:
        for r in rows:
            # payload already parsed to dict; strip entries body to save transfer
            payload = r.get("payload") or {}
            entry_count = len(payload.get("entries") or [])
            r["entry_count"] = entry_count
            r["payload"] = {"entry_count": entry_count}
    return ok(rows)


@router.post("/forbidden-lexicons")
async def upsert_forbidden_lexicon(body: UpsertForbiddenLexiconRequest):
    payload = body.model_dump()
    project_id = payload["project_id"]
    entries = payload.get("entries") or []
    # Normalize (string -> literal, dict with pattern validation)
    import re as _re
    normalized: list[dict] = []
    for raw in entries:
        if isinstance(raw, str):
            if raw.strip():
                normalized.append({"pattern": raw.strip(), "match_type": "literal"})
        elif isinstance(raw, dict):
            if not raw.get("pattern"):
                continue
            match_type = (raw.get("match_type") or "literal").lower()
            if match_type == "regex":
                try:
                    _re.compile(raw["pattern"])
                except _re.error as exc:
                    return err(f"正则 {raw['pattern']!r} 不合法: {exc}", status_code=400)
            normalized.append({
                "pattern": str(raw["pattern"]),
                "match_type": match_type,
                "category": raw.get("category") or "word",
                "severity": raw.get("severity") or "block",
                "note": raw.get("note") or "",
                "whitelist_contexts": raw.get("whitelist_contexts") or [],
            })
    from app.services.assets.assets_service import AssetsService
    svc = AssetsService()
    asset_id = payload.get("asset_id")
    title = (payload.get("title") or "").strip()
    payload_json = {"entries": normalized}
    if asset_id:
        existing = svc.find(asset_id, project_id=project_id)
        if not existing:
            return err(f"未找到 asset_id={asset_id}", status_code=404)
        result = svc.update(
            asset_id,
            scope=existing.get("scope", "project"),
            project_id=existing.get("project_id"),
            title=title or existing.get("title") or "禁词表",
            payload=payload_json,
        )
        return ok(result)
    if not title:
        return err("新建禁词资产必须提供 title", status_code=400)
    created = svc.create(
        scope="project",
        project_id=project_id,
        asset_type="forbidden_lexicon",
        title=title,
        summary=f"{len(normalized)} 条禁用规则",
        payload=payload_json,
        source_kind="manual",
    )
    return ok(created)


@router.delete("/forbidden-lexicons/{asset_id}")
async def delete_forbidden_lexicon(asset_id: str, project_id: str = ""):
    from app.services.assets.assets_service import AssetsService
    svc = AssetsService()
    existing = svc.find(asset_id, project_id=project_id)
    if not existing:
        return err(f"未找到 asset_id={asset_id}", status_code=404)
    svc.delete(asset_id, scope=existing.get("scope", "project"), project_id=existing.get("project_id"))
    return ok(None)
