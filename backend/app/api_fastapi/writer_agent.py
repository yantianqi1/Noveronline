"""Native FastAPI writer-agent routes."""

from __future__ import annotations

import asyncio
import json
import logging
import time

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse, StreamingResponse

from .common import err, ok
from app.schemas.asset_types import AssetType
from app.schemas.writer_agent_schemas import (
    ApplyReviewerRequest,
    CompileChapterRequest,
    CreateBookPlanRequest,
    CreateChapterRequest,
    CreatePresetRequest,
    ManuscriptCommitRequest,
    MoveBlockRequest,
    OneClickAlignWordsRequest,
    OneClickCompleteOutlineRequest,
    OneClickContinueChapterRequest,
    OneClickFillRelationshipsRequest,
    OneClickScanLexiconRequest,
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
logger = logging.getLogger(__name__)

# Interval between SSE keep-alive comment lines. Long-running writer runs (60s+
# with many tool calls) can stall intermediate proxies/load balancers that idle
# out silent connections, which triggers a mid-stream disconnect and, on the
# client side, a retry that duplicates the generated prose. Sending a comment
# line periodically keeps the socket hot without interfering with event parsing.
SSE_KEEPALIVE_INTERVAL_SECONDS = 15.0


def sse_response(generator):
    return StreamingResponse(generator, media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


async def _with_keepalive(source):
    """Wrap an async event generator with periodic SSE comment heartbeats."""
    queue: asyncio.Queue[object] = asyncio.Queue()
    sentinel_done = object()
    sentinel_error: dict[str, object] = {}

    async def _producer():
        try:
            async for item in source:
                await queue.put(item)
        except Exception as exc:  # noqa: BLE001
            sentinel_error["exc"] = exc
            await queue.put(sentinel_error)
            return
        await queue.put(sentinel_done)

    task = asyncio.create_task(_producer())
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
                continue
            if item is sentinel_done:
                return
            if item is sentinel_error:
                exc = sentinel_error.get("exc")
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                return
            yield item
    finally:
        if not task.done():
            task.cancel()


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
        terminated = False
        try:
            async for event in orchestrator.run(payload):
                if event.get("type") == "done":
                    terminated = True
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if not terminated:
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return sse_response(_with_keepalive(events()))


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
        terminated = False
        try:
            async for event in loop.run(user_msg):
                if event.get("type") == "done":
                    terminated = True
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if not terminated:
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return sse_response(_with_keepalive(events()))


def _int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@router.post("/apply-reviewer")
async def apply_reviewer(body: ApplyReviewerRequest):
    """Re-generate a scene by applying the user-selected reviewer suggestions.

    Streams ``writer_token`` events just like ``/run`` so the frontend can
    display the rewrite in real time, then upserts over the existing
    ``scene_id`` (PostProcessor resolves order collisions automatically).
    Dedup extraction runs again on the rewrite so future chapters benefit.
    """
    payload = body.model_dump()
    project_id = payload.get("project_id")
    scene_id = payload.get("scene_id")
    if not project_id or not scene_id:
        return err("缺少 project_id 或 scene_id", status_code=400)

    draft = (payload.get("draft") or "").strip()
    accepted_issues = payload.get("accepted_issues") or []
    if not draft or not accepted_issues:
        return err("缺少 draft 或 accepted_issues", status_code=400)

    writing_brief = dict(payload.get("writing_brief") or {})
    chapter_id = payload.get("chapter_id") or ""
    chapter_order = _int(payload.get("chapter_order"), 0)
    scene_order = _int(payload.get("scene_order"), 1)
    preset_id = payload.get("preset_id") or ""
    pov_entity_id = payload.get("pov_entity_id") or ""
    involved = payload.get("involved_entity_ids") or []

    # Frontend currently posts writing_brief: {} for this endpoint (the brief is
    # already persisted server-side on the initial write). Without backfilling,
    # the composer would run with a bare constraint list — losing POV, character
    # profiles, relationships, world rules, and anti-cliché context — and the
    # rewrite quality would drop noticeably. Pull the stored brief from the scene
    # row and use it as the base; any fields the client explicitly provides
    # still win.
    if not writing_brief or not writing_brief.get("pov"):
        from app.database import get_engine as _backfill_engine
        from app.repositories.scene_repo import SceneRepository as _SceneRepo
        try:
            scene_row = _SceneRepo(_backfill_engine()).get_scene(project_id, scene_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("apply_reviewer: failed to load scene %s: %s", scene_id, exc)
            scene_row = None
        if scene_row and scene_row.get("writing_brief_json"):
            try:
                stored = json.loads(scene_row["writing_brief_json"])
                if isinstance(stored, dict):
                    # stored is the base; client-provided fields override.
                    writing_brief = {**stored, **writing_brief}
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "apply_reviewer: failed to parse stored writing_brief_json for %s: %s",
                    scene_id,
                    exc,
                )
    logger.info(
        "apply_reviewer brief keys: %s (scene_id=%s)",
        sorted(writing_brief.keys()),
        scene_id,
    )

    # Inject the accepted rewrite suggestions into the brief's constraints,
    # formatted so the writer composer sees them as hard rules alongside the
    # existing static anti-cliché block.
    constraint_lines = list(writing_brief.get("constraints") or [])
    constraint_lines.append(
        "审校员已指出以下问题，本稿必须逐条改写（保持场景走向不变）："
    )
    for issue in accepted_issues:
        original = (issue.get("original") or "").strip()
        suggestion = (issue.get("suggestion") or "").strip()
        reason = (issue.get("reason") or "").strip()
        if original and suggestion:
            constraint_lines.append(
                f"- 将『{original}』改写为『{suggestion}』（{reason or '审校建议'}）"
            )
        elif suggestion:
            constraint_lines.append(f"- 按下述建议改写：{suggestion}")
    writing_brief["constraints"] = constraint_lines
    writing_brief["original_text"] = draft  # triggers rewrite-aware layout in writer prompt

    from app.services.llm_router import LlmRouter
    from app.services.writer_agent.post_processor import PostProcessor
    from app.services.writer_agent.reviewer import WriterReviewer
    from app.services.writer_agent.writer import WriterComposer
    from app.repositories.preset_repo import PresetRepository
    from app.database import get_engine as _get_engine

    # Resolve preset_prompt the same way orchestrator does.
    def _resolve_preset() -> str:
        if not preset_id and not project_id:
            return ""
        try:
            presets = PresetRepository(_get_engine()).list_presets(project_id or "")
        except Exception:  # noqa: BLE001
            presets = []
        if preset_id:
            for p in presets:
                if p.get("preset_id") == preset_id:
                    return p.get("system_prompt") or ""
        for p in presets:
            if p.get("is_default"):
                return p.get("system_prompt") or ""
        return (
            "你是一名资深小说家。根据提供的写作指令创作小说正文。"
            "只输出正文，对白贴合角色，严格遵守既有设定，推进剧情有因果。"
        )

    preset_prompt = _resolve_preset()

    async def events():
        t0 = time.monotonic()

        def _stamp():
            return {"ts": time.strftime("%H:%M:%S"), "elapsed_ms": int((time.monotonic() - t0) * 1000)}

        yield f"data: {json.dumps({'type': 'orchestrator_status', 'phase': 'rewriting', 'message': '按审校建议改写中...', **_stamp()}, ensure_ascii=False)}\n\n"

        composer = WriterComposer(LlmRouter())
        full_text = ""
        terminated = False
        try:
            async for chunk in composer.compose_stream(writing_brief, preset_prompt):
                full_text += chunk
                yield f"data: {json.dumps({'type': 'writer_token', 'token': chunk}, ensure_ascii=False)}\n\n"

            processor = PostProcessor()
            result = await asyncio.to_thread(
                processor.process,
                project_id=project_id,
                chapter_id=chapter_id,
                scene_order=scene_order,
                scene_id=scene_id,
                content=full_text,
                writing_brief=writing_brief,
                title=writing_brief.get("scene_focus", ""),
                pov_entity_id=pov_entity_id,
                location=writing_brief.get("location"),
                involved_entities_json=json.dumps(involved, ensure_ascii=False),
            )

            # Re-extract dedup patterns from the rewrite so subsequent chapters
            # learn from the improved text, not the discarded original.
            if chapter_order and full_text.strip():
                try:
                    from app.services.writer_agent.dedup_extractor import DedupExtractor as _Extractor
                    asyncio.create_task(
                        _Extractor().extract_and_save(
                            project_id=project_id,
                            chapter_order=chapter_order,
                            scene_id=scene_id,
                            content=full_text,
                            scene_order=result.get("scene_order", scene_order),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    pass  # best-effort

            # Re-run reviewer on the rewrite so the frontend can loop if issues remain.
            review_payload = await WriterReviewer().review(
                draft=full_text,
                writing_brief=writing_brief,
                prev_narrative=writing_brief.get("recent_narrative", "") or "",
                dedup_constraints=writing_brief.get("dedup_constraints") or {},
            )
            yield f"data: {json.dumps({'type': 'reviewer_feedback', 'feedback': review_payload, 'scene_id': scene_id, 'chapter_id': chapter_id, 'chapter_order': chapter_order, 'scene_order': result.get('scene_order', scene_order), **_stamp()}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'scene_id': scene_id, 'word_count': len(full_text), **result, **_stamp()}, ensure_ascii=False)}\n\n"
            terminated = True
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if not terminated:
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return sse_response(_with_keepalive(events()))
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@router.get("/scenes/{chapter_id}")
async def list_scenes(chapter_id: str, project_id: str = ""):
    from app.services.writer_agent.scene_service import SceneService
    return ok(SceneService().list_scenes(project_id, chapter_id))


@router.post("/scenes/{chapter_id}")
async def create_scene_route(chapter_id: str, body: dict):
    """Create a new scene under the given chapter. Payload accepts the
    SceneProposal subset emitted by the writer tool-render cards
    (scene_order, title, summary -> content, pov, characters, key_events)."""
    if not body.get("project_id"):
        return err("缺少 project_id", status_code=400)
    from app.services.writer_agent.scene_service import SceneService
    svc = SceneService()
    # Map card fields to service signature; unknown extras are ignored.
    content_parts: list[str] = []
    if body.get("summary"):
        content_parts.append(f"【概述】{body['summary']}")
    if body.get("key_events"):
        content_parts.append(f"【关键事件】{body['key_events']}")
    if body.get("notes"):
        content_parts.append(f"【备注】{body['notes']}")
    content = body.get("content") or ("\n\n".join(content_parts) if content_parts else "")
    scene = svc.create_scene(
        project_id=body["project_id"],
        chapter_id=chapter_id,
        title=body.get("title") or "",
        content=content,
        scene_order=body.get("scene_order"),
        pov_entity_id=body.get("pov_entity_id") or body.get("pov") or None,
        location=body.get("setting") or body.get("location") or None,
    )
    return ok(scene)


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


@router.get("/book-plans/{plan_id}/status")
async def get_book_plan_status(plan_id: str):
    """Aggregate plan progress for the writer StatusBar."""
    from app.services.writer_agent.book_plan_service import BookPlanService
    status = BookPlanService().get_plan_status(plan_id)
    return ok(status) if status else err("book_plan 不存在", status_code=404)


@router.get("/book-plans/active/by-project")
async def get_active_book_plan(project_id: str = ""):
    """Return the most recently updated active plan for a project (or null)."""
    if not project_id:
        return err("缺少 project_id", status_code=400)
    from app.services.writer_agent.book_plan_service import BookPlanService
    plan = BookPlanService().get_active_plan(project_id)
    return ok(plan)


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


# ---------------------------------------------------------------------------
# One-click buttons (W-3 §4.4). Each streams SSE events from an OneClickRunner
# that drives AgentLoop with a hard-coded system prompt + propose_* whitelist.
# Cards are never written to DB — frontend adopts them by dispatching to
# existing API clients based on render.type.
# ---------------------------------------------------------------------------


def _one_click_stream(runner, context: dict):
    """Wrap a OneClickRunner instance with the standard SSE envelope."""

    async def events():
        terminated = False
        try:
            async for event in runner.run(context):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event.get("type") == "summary":
                    # summary is the runner's final event — convert to done.
                    yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                    terminated = True
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"
        finally:
            if not terminated:
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return sse_response(_with_keepalive(events()))


@router.post("/one-click/complete-outline")
async def one_click_complete_outline(body: OneClickCompleteOutlineRequest):
    payload = body.model_dump()
    if not payload.get("project_id") or not payload.get("chapter_id"):
        return err("缺少 project_id 或 chapter_id", status_code=400)
    from app.services.writer_agent.one_click import OutlineCompleterRunner

    return _one_click_stream(OutlineCompleterRunner(), payload)


@router.post("/one-click/align-words")
async def one_click_align_words(body: OneClickAlignWordsRequest):
    payload = body.model_dump()
    if not payload.get("project_id") or not payload.get("chapter_id"):
        return err("缺少 project_id 或 chapter_id", status_code=400)
    if not payload.get("target_word_count"):
        return err("缺少 target_word_count", status_code=400)
    from app.services.writer_agent.one_click import WordAlignerRunner

    return _one_click_stream(WordAlignerRunner(), payload)


@router.post("/one-click/scan-lexicon")
async def one_click_scan_lexicon(body: OneClickScanLexiconRequest):
    payload = body.model_dump()
    if not payload.get("project_id") or not payload.get("chapter_id"):
        return err("缺少 project_id 或 chapter_id", status_code=400)
    from app.services.writer_agent.one_click import LexiconCleanerRunner

    return _one_click_stream(LexiconCleanerRunner(), payload)


@router.post("/one-click/fill-relationships")
async def one_click_fill_relationships(body: OneClickFillRelationshipsRequest):
    payload = body.model_dump()
    if not payload.get("project_id") or not payload.get("chapter_id"):
        return err("缺少 project_id 或 chapter_id", status_code=400)
    from app.services.writer_agent.one_click import RelationshipFillerRunner

    return _one_click_stream(RelationshipFillerRunner(), payload)


@router.post("/one-click/continue-chapter")
async def one_click_continue_chapter(body: OneClickContinueChapterRequest):
    payload = body.model_dump()
    if not payload.get("project_id") or not payload.get("chapter_id"):
        return err("缺少 project_id 或 chapter_id", status_code=400)
    from app.services.writer_agent.one_click import ChapterContinuerRunner

    return _one_click_stream(ChapterContinuerRunner(), payload)


@router.get("/forbidden-lexicons")
async def list_forbidden_lexicons(project_id: str = "", include_entries: bool = False):
    if not project_id:
        return err("缺少 project_id", status_code=400)
    from app.services.assets.assets_service import AssetsService
    svc = AssetsService()
    rows = svc.list_merged(
        project_id=project_id,
        asset_type=AssetType.FORBIDDEN_LEXICON.value,
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
        asset_type=AssetType.FORBIDDEN_LEXICON.value,
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
