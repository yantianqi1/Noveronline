"""小说分析 API"""

import traceback

from flask import jsonify, request

from . import novel_bp
from .novel_graph_defaults import graph_entity_types
from ..models.project import ProjectManager
from ..services.archive_library_service import ArchiveLibraryService
from ..services.narrative_entity_archivist import NarrativeEntityArchivist
from ..services.parallel_world_config_generator import ParallelWorldConfigGenerator
from ..services.plot_inspiration_engine import PlotInspirationEngine
from ..services.worldline_engine_factory import build_worldline_engine
from ..services.zep_entity_reader import EntityNode, ZepEntityReader

archive_library_service = ArchiveLibraryService()

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
@novel_bp.route("/archives/generate", methods=["POST"])
def generate_archives():
    try:
        data = request.get_json() or {}
        graph_id, project = _resolve_project_context(data)
        use_llm = data.get("use_llm", True)
        entity_types = graph_entity_types(data.get("entity_types"), graph_id)
        archivist = NarrativeEntityArchivist()
        payload_entity_types = []

        if graph_id:
            reader = ZepEntityReader()
            filtered = reader.filter_defined_entities(
                graph_id=graph_id,
                defined_entity_types=entity_types,
                enrich_with_edges=True,
            )
            archives = archivist.generate_archives_from_entities(filtered.entities, use_llm=use_llm)
            payload_entity_types = list(filtered.entity_types)
        else:
            seed_analysis = _load_seed_analysis(project)
            if not seed_analysis:
                raise ValueError("当前项目既没有 graph_id，也没有可用的 seed_analysis.json")
            archives = archivist.generate_archives_from_seed_analysis(seed_analysis)
            payload_entity_types = ["Character", "Organization"]

        payload = {
            "graph_id": graph_id,
            "project_id": project.project_id if project else None,
            "count": len(archives),
            "entity_types": payload_entity_types,
            "archives": [item.to_dict() for item in archives],
        }

        if project:
            ProjectManager.save_project_json(project.project_id, "narrative_archives.json", payload)
            synced = archive_library_service.sync_project_archives(project.project_id, force=True)
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
            analysis_goal = "分析当前小说世界在变量注入后的平行世界演变"

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
            branch = next((item for item in session.branches if item.branch_id == branch_id), None) if branch_id else session.branches[0]
            if not branch:
                return jsonify({"success": False, "error": f"分支不存在: {branch_id}"}), 404
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
                "branch_id": branch_id,
                "result": result,
            },
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500
