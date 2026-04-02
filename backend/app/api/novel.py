"""小说分析 API"""

import json
import traceback

from flask import Response, jsonify, request

from . import novel_bp
from .novel_graph_defaults import graph_entity_types
from ..models.project import ProjectManager
from ..services.archive_candidate_builder import ArchiveCandidateBuilder
from ..services.archive_library_service import ArchiveLibraryService
from ..services.chapter_card_generator import ChapterCardGenerator
from ..services.chapter_context_pack_builder import ChapterContextPackBuilder
from ..services.chapter_continuity_service import ChapterContinuityService
from ..services.chapter_meta_service import ChapterMetaService
from ..services.agents.draft import NovelDraftOrchestrator
from ..services.llm_router import LlmRouter
from ..services.agents.draft.reviewer_agent import REVIEWER_SYSTEM_PROMPT
from ..services.narrative_entity_archivist import NarrativeEntityArchivist
from ..services.parallel_world_config_generator import ParallelWorldConfigGenerator
from ..services.plot_inspiration_engine import PlotInspirationEngine
from ..services.worldline_engine_factory import build_worldline_engine
from ..services.worldline_single_world import current_world, resolve_branch_id
from ..services.zep_entity_reader import EntityNode, ZepEntityReader

archive_candidate_builder = ArchiveCandidateBuilder()
chapter_context_pack_builder = ChapterContextPackBuilder()


def _archive_library_service() -> ArchiveLibraryService:
    return ArchiveLibraryService()


def _chapter_context_service() -> ChapterContextPackBuilder:
    return chapter_context_pack_builder

def _resolve_project_context(data):
    project_id = data.get("project_id")
    graph_id = data.get("graph_id")

    project = None
    if project_id:
        project = ProjectManager.get_project(project_id)
        if not project:
            raise ValueError(f"项目不存在: {project_id}")
        graph_id = graph_id or project.graph_id

    return graph_id, project

def _load_seed_analysis(project):
    if not project:
        return None
    return ProjectManager.load_project_json(project.project_id, "seed_analysis.json")


def _build_entities_from_seed_analysis(seed_analysis):
    entities = []
    for item in seed_analysis.get("characters", []):
        entities.append(
            EntityNode(
                uuid=f"seed_character_{item.get('name', '')}",
                name=item.get("name", ""),
                labels=["Entity", "Character"],
                summary=item.get("profile_summary", ""),
                attributes={
                    "importance_tier": item.get("importance_tier", "supporting"),
                    "identity_hint": item.get("identity_hint", "角色"),
                },
            )
        )
    for item in seed_analysis.get("organizations", []):
        entities.append(
            EntityNode(
                uuid=f"seed_org_{item.get('name', '')}",
                name=item.get("name", ""),
                labels=["Entity", "Organization"],
                summary=item.get("summary", ""),
                attributes={
                    "organization_type": item.get("organization_type", "organization"),
                    "importance_tier": item.get("importance_tier", "major"),
                },
            )
        )
    return entities


def _candidate_override_map(data):
    overrides = {}
    for item in data.get("tier_overrides", []) or []:
        entity_uuid = str(item.get("entity_uuid") or item.get("candidate_id") or "").strip()
        importance_tier = str(item.get("importance_tier") or "").strip()
        if entity_uuid and importance_tier:
            overrides[entity_uuid] = importance_tier
    for item in data.get("candidate_snapshot", []) or []:
        entity_uuid = str(item.get("entity_uuid") or item.get("candidate_id") or "").strip()
        importance_tier = str(item.get("selected_importance_tier") or "").strip()
        if entity_uuid and importance_tier:
            overrides.setdefault(entity_uuid, importance_tier)
    return overrides


def _archive_candidates(graph_id, project, entity_types):
    if graph_id:
        reader = ZepEntityReader()
        filtered = reader.filter_defined_entities(
            graph_id=graph_id,
            defined_entity_types=entity_types,
            enrich_with_edges=True,
        )
        return (
            archive_candidate_builder.build_from_entities(filtered.entities),
            {item.uuid: item for item in filtered.entities},
            list(filtered.entity_types) + ["Relationship"],
        )
    seed_analysis = _load_seed_analysis(project)
    if not seed_analysis:
        raise ValueError("当前项目既没有 graph_id，也没有可用的 seed_analysis.json")
    return archive_candidate_builder.build_from_seed_analysis(seed_analysis), {}, ["Character", "Organization", "Relationship"]


@novel_bp.route("/archives/candidates", methods=["POST"])
def list_archive_candidates():
    try:
        data = request.get_json() or {}
        graph_id, project = _resolve_project_context(data)
        entity_types = graph_entity_types(data.get("entity_types"), graph_id)
        candidates, _, payload_entity_types = _archive_candidates(graph_id, project, entity_types)
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id if project else None,
                "graph_id": graph_id,
                "count": len(candidates),
                "entity_types": payload_entity_types,
                "candidates": candidates,
            },
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@novel_bp.route("/archives/generate", methods=["POST"])
def generate_archives():
    try:
        data = request.get_json() or {}
        graph_id, project = _resolve_project_context(data)
        use_llm = data.get("use_llm", True)
        entity_types = graph_entity_types(data.get("entity_types"), graph_id)
        archivist = NarrativeEntityArchivist(candidate_builder=archive_candidate_builder)
        candidates, entity_lookup, payload_entity_types = _archive_candidates(graph_id, project, entity_types)
        archives = archivist.generate_archives_from_candidates(
            candidates,
            use_llm=use_llm,
            tier_overrides=_candidate_override_map(data),
            entity_lookup=entity_lookup,
        )

        payload = {
            "graph_id": graph_id,
            "project_id": project.project_id if project else None,
            "count": len(archives),
            "entity_types": payload_entity_types,
            "archives": [item.to_dict() for item in archives],
        }

        if project:
            ProjectManager.save_project_json(project.project_id, "narrative_archives.json", payload)
            synced = _archive_library_service().sync_project_archives(project.project_id, force=True)
            archive_map = {item["entity_uuid"]: item["archive_id"] for item in synced}
            payload["archives"] = [
                {
                    **item,
                    "archive_id": archive_map.get(item.get("entity_uuid")),
                }
                for item in payload["archives"]
            ]

        return jsonify({"success": True, "data": payload})
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@novel_bp.route("/parallel-world/config", methods=["POST"])
def generate_parallel_world_config():
    try:
        data = request.get_json() or {}
        graph_id, project = _resolve_project_context(data)
        variables = data.get("variables", [])
        use_llm = data.get("use_llm", True)
        entity_types = graph_entity_types(data.get("entity_types"), graph_id)
        branch_count = data.get("branch_count")
        focus_question = data.get("focus_question")

        analysis_goal = focus_question
        if not analysis_goal and project:
            analysis_goal = project.analysis_goal
        if not analysis_goal:
            analysis_goal = "分析当前小说世界在变量注入后的持续演化"

        if graph_id:
            reader = ZepEntityReader()
            filtered = reader.filter_defined_entities(
                graph_id=graph_id,
                defined_entity_types=entity_types,
                enrich_with_edges=False,
            )
            entities = filtered.entities
        else:
            seed_analysis = _load_seed_analysis(project)
            if not seed_analysis:
                raise ValueError("当前项目既没有 graph_id，也没有可用的 seed_analysis.json")
            entities = _build_entities_from_seed_analysis(seed_analysis)

        generator = ParallelWorldConfigGenerator()
        config = generator.generate(
            analysis_goal=analysis_goal,
            entities=entities,
            variables=variables,
            branch_count=branch_count,
            use_llm=use_llm,
        )

        if project:
            ProjectManager.save_project_json(project.project_id, "parallel_world_config.json", config.to_dict())

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id if project else None,
                "graph_id": graph_id,
                "config": config.to_dict(),
            },
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500
@novel_bp.route("/seed-analysis/<project_id>", methods=["GET"])
def get_seed_analysis(project_id: str):
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404
        seed_analysis = _load_seed_analysis(project)
        if not seed_analysis:
            return jsonify({"success": False, "error": "该项目尚未生成 seed_analysis"}), 404
        return jsonify({"success": True, "data": seed_analysis})
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500
@novel_bp.route("/seed-analysis", methods=["POST"])
def run_seed_analysis():
    try:
        data = request.get_json() or {}
        _, project = _resolve_project_context(data)
        if not project:
            return jsonify({"success": False, "error": "请提供 project_id"}), 400

        seed_analysis = _load_seed_analysis(project)
        if not seed_analysis:
            extracted_text = ProjectManager.get_extracted_text(project.project_id)
            if not extracted_text:
                return jsonify({"success": False, "error": "项目缺少可用文本，无法生成种子分析"}), 400
            from ..services.novel_seed_analyzer import NovelSeedAnalyzer

            analyzer = NovelSeedAnalyzer()
            seed_analysis = analyzer.analyze_text(
                text=extracted_text,
                analysis_goal=data.get("analysis_goal") or project.analysis_goal or "",
                project_name=project.name,
            )
            ProjectManager.save_project_json(project.project_id, "seed_analysis.json", seed_analysis)

        return jsonify({"success": True, "data": seed_analysis})
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500
@novel_bp.route("/plot/inspiration", methods=["POST"])
def generate_plot_inspiration():
    try:
        data = request.get_json() or {}
        graph_id, project = _resolve_project_context(data)
        session_id = data.get("session_id")
        branch_id = data.get("branch_id")
        creator_prompt = (data.get("creator_prompt") or "").strip()
        if not creator_prompt:
            return jsonify({"success": False, "error": "请提供 creator_prompt"}), 400

        branch_summary = {}
        actors = {}
        recent_events = []
        variables = []
        focus_question = project.analysis_goal if project and project.analysis_goal else ""

        if session_id:
            engine = build_worldline_engine()
            session = engine.get_session(session_id, project_id=project.project_id if project else None, graph_id=graph_id)
            if not session:
                return jsonify({"success": False, "error": f"世界线会话不存在: {session_id}"}), 404
            focus_question = session.focus_question or focus_question
            variables = [item.to_dict() for item in session.world_variables]
            resolve_branch_id(branch_id)
            branch = current_world(session)
            branch_summary = {
                "branch_id": branch.branch_id,
                "title": branch.title,
                "core_change": branch.core_change,
            }
            actors = branch.actor_states
            recent_events = [item.to_dict() for item in branch.timeline[-4:]]
        else:
            seed_analysis = _load_seed_analysis(project) if project else None
            if seed_analysis:
                actors = {
                    item.get("name", ""): {
                        "drive": "推动自身命运与故事主线",
                        "tension": item.get("profile_summary", ""),
                    }
                    for item in seed_analysis.get("characters", [])[:6]
                    if item.get("name")
                }
                recent_events = seed_analysis.get("chapter_beats", [])[:4]
            branch_summary = {"title": "原始世界线", "core_change": focus_question or "沿原始小说主线推进"}

        engine = PlotInspirationEngine()
        result = engine.generate(
            focus_question=focus_question,
            branch_summary=branch_summary,
            creator_prompt=creator_prompt,
            variables=variables,
            recent_events=recent_events,
            actors=actors,
        )

        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id if project else None,
                "graph_id": graph_id,
                "session_id": session_id,
                "branch_id": branch.branch_id if session_id else None,
                "result": result,
            },
        })
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@novel_bp.route("/chapter-context/options", methods=["GET"])
def chapter_context_options():
    try:
        project_id = (request.args.get("project_id") or "").strip()
        if not project_id:
            return jsonify({"success": False, "error": "请提供 project_id"}), 400
        return jsonify({"success": True, "data": _chapter_context_service().build_options(project_id)})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@novel_bp.route("/chapter-context", methods=["POST"])
def build_chapter_context():
    try:
        data = request.get_json() or {}
        return jsonify({"success": True, "data": _chapter_context_service().build(data)})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@novel_bp.route("/reviewer-rules", methods=["GET"])
def get_reviewer_rules():
    """获取项目的自定义审校规则。"""
    project_id = request.args.get("project_id", "")
    if not project_id:
        return jsonify({"success": False, "error": "需要 project_id"}), 400
    try:
        data = ProjectManager.load_project_json(project_id, "reviewer_rules.json")
        custom_prompt = (data or {}).get("custom_prompt", "")
        return jsonify({
            "success": True,
            "data": {
                "custom_prompt": custom_prompt,
                "default_prompt": REVIEWER_SYSTEM_PROMPT,
                "is_custom": bool(custom_prompt),
            },
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@novel_bp.route("/reviewer-rules", methods=["PUT"])
def save_reviewer_rules():
    """保存项目的自定义审校规则。"""
    data = request.get_json() or {}
    project_id = data.get("project_id", "")
    custom_prompt = data.get("custom_prompt", "")
    if not project_id:
        return jsonify({"success": False, "error": "需要 project_id"}), 400
    try:
        from datetime import datetime
        payload = {
            "custom_prompt": custom_prompt,
            "updated_at": datetime.now().isoformat(),
        }
        ProjectManager.save_project_json(project_id, "reviewer_rules.json", payload)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@novel_bp.route("/draft/generate", methods=["POST"])
def draft_generate():
    """SSE 端点：多 Agent 协同生成小说正文。"""
    data = request.get_json() or {}
    orchestrator = NovelDraftOrchestrator()

    def event_stream():
        try:
            for event in orchestrator.generate_stream(data):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error_event = json.dumps(
                {"type": "error", "message": str(exc)},
                ensure_ascii=False,
            )
            yield f"data: {error_event}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@novel_bp.route("/draft/revise", methods=["POST"])
def draft_revise():
    """SSE 端点：用户驱动的修订流程（重写 + 重审）。"""
    data = request.get_json() or {}
    orchestrator = NovelDraftOrchestrator()

    def event_stream():
        try:
            for event in orchestrator.revise_stream(data):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error_event = json.dumps(
                {"type": "error", "message": str(exc)},
                ensure_ascii=False,
            )
            yield f"data: {error_event}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@novel_bp.route("/draft/finalize", methods=["POST"])
def draft_finalize():
    """定稿端点：回写章节正文，并以结构化章节卡更新历史召回数据。"""
    try:
        data = request.get_json() or {}
        project_id = (data.get("project_id") or "").strip()
        chapter_order = data.get("chapter_order", data.get("chapter_index"))
        chapter_text = (data.get("chapter_text") or "").strip()
        chapter_card_payload = data.get("chapter_card")

        if not project_id:
            return jsonify({"success": False, "error": "请提供 project_id"}), 400
        if chapter_order is None:
            return jsonify({"success": False, "error": "请提供 chapter_order"}), 400
        if not chapter_text and not isinstance(chapter_card_payload, dict):
            return jsonify({"success": False, "error": "请提供 chapter_text 或 chapter_card"}), 400

        chapter_order = int(chapter_order)
        existing_cards = _load_chapter_cards(project_id)
        chapter = _build_finalize_chapter_input(data, chapter_order, chapter_text, existing_cards)
        chapter_card = _resolve_finalize_chapter_card(project_id, chapter, chapter_card_payload, existing_cards)
        cards_payload = _upsert_project_chapter_cards(project_id, chapter_card, existing_cards)
        continuity = ChapterContinuityService().build_from_chapter_cards(cards_payload["chapters"])
        ProjectManager.save_project_json(project_id, "chapter_continuity.json", continuity)
        _upsert_project_chapter_segment(project_id, chapter)
        story_memory = ProjectManager.load_project_json(project_id, "story_memory.json") or {}
        ChapterMetaService().replace_project_chapter_cards(
            project_id,
            cards_payload["chapters"],
            world_rules=story_memory.get("world_rules", []),
        )

        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "chapter_order": chapter_order,
                "chapter_id": chapter_card["chapter_id"],
                "message": "章节卡已回写并同步历史召回",
            },
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


def _load_chapter_cards(project_id):
    payload = ProjectManager.load_project_json(project_id, "chapter_cards.json") or {}
    return sorted(payload.get("chapters", []), key=lambda item: int(item.get("chapter_order") or item.get("order") or 0))


def _build_finalize_chapter_input(data, chapter_order, chapter_text, existing_cards):
    chapter_id = str(data.get("chapter_id") or f"chapter_{chapter_order:04d}").strip()
    title = str(data.get("title") or _existing_card_title(existing_cards, chapter_order) or f"第{chapter_order}章").strip()
    return {
        "chapter_id": chapter_id,
        "order": chapter_order,
        "title": title,
        "content": chapter_text,
    }


def _resolve_finalize_chapter_card(project_id, chapter, explicit_card, existing_cards):
    generator = ChapterCardGenerator(llm_router=LlmRouter())
    if isinstance(explicit_card, dict):
        return generator._normalize_card(chapter, explicit_card)
    story_memory = ProjectManager.load_project_json(project_id, "story_memory.json") or {}
    block_analyses = ProjectManager.load_project_json(project_id, "block_analyses.json") or {"blocks": []}
    previous_cards = [
        item for item in existing_cards
        if int(item.get("chapter_order") or item.get("order") or 0) < int(chapter["order"])
    ]
    return generator.generate_single_card(chapter, story_memory, block_analyses, previous_cards)


def _upsert_project_chapter_cards(project_id, chapter_card, existing_cards):
    remaining = [
        item for item in existing_cards
        if int(item.get("chapter_order") or item.get("order") or 0) != int(chapter_card["chapter_order"])
    ]
    remaining.append(chapter_card)
    chapters = sorted(remaining, key=lambda item: int(item.get("chapter_order") or item.get("order") or 0))
    payload = {"chapter_count": len(chapters), "chapters": chapters}
    ProjectManager.save_project_json(project_id, "chapter_cards.json", payload)
    return payload


def _upsert_project_chapter_segment(project_id, chapter):
    payload = ProjectManager.load_project_json(project_id, "chapter_segments.json") or {"chapter_count": 0, "chapters": []}
    chapters = []
    matched = False
    for item in payload.get("chapters", []):
        if int(item.get("order") or 0) != int(chapter["order"]):
            chapters.append(item)
            continue
        matched = True
        chapters.append({**item, "chapter_id": chapter["chapter_id"], "order": chapter["order"], "title": chapter["title"], "content": chapter["content"] or item.get("content") or item.get("text") or ""})
    if not matched:
        chapters.append({"chapter_id": chapter["chapter_id"], "order": chapter["order"], "title": chapter["title"], "content": chapter["content"]})
    chapters = sorted(chapters, key=lambda item: int(item.get("order") or 0))
    ProjectManager.save_project_json(project_id, "chapter_segments.json", {"chapter_count": len(chapters), "chapters": chapters})


def _existing_card_title(existing_cards, chapter_order):
    for item in existing_cards:
        if int(item.get("chapter_order") or item.get("order") or 0) == int(chapter_order):
            return item.get("title", "")
    return ""
