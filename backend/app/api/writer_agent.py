"""Writer Agent API blueprint."""
import json
import traceback

from flask import Blueprint, Response, jsonify, request

writer_agent_bp = Blueprint("writer_agent", __name__)


def _error_response(exc, status_code=500):
    return jsonify({
        "success": False,
        "error": str(exc),
        "traceback": traceback.format_exc(),
    }), status_code


# ---- Core Writing (SSE) ----

@writer_agent_bp.route("/run", methods=["POST"])
def run_writer_agent():
    """Execute a writing task. Returns SSE stream."""
    data = request.get_json() or {}
    from ..services.writer_agent.orchestrator import WriterOrchestrator
    orchestrator = WriterOrchestrator()

    def event_stream():
        try:
            for event in orchestrator.run(data):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return Response(
        event_stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---- Scene CRUD ----

@writer_agent_bp.route("/scenes/<chapter_id>", methods=["GET"])
def list_scenes(chapter_id):
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.scene_service import SceneService
        scenes = SceneService().list_scenes(project_id, chapter_id)
        return jsonify({"success": True, "data": scenes})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/scenes/detail/<scene_id>", methods=["GET"])
def get_scene_detail(scene_id):
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.scene_service import SceneService
        scene = SceneService().get_scene(project_id, scene_id)
        return jsonify({"success": True, "data": scene})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/scenes/<scene_id>", methods=["PUT"])
def update_scene(scene_id):
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id", "")
        from ..services.writer_agent.scene_service import SceneService
        result = SceneService().update_scene(
            project_id, scene_id,
            content=data.get("content"),
            title=data.get("title"),
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/scenes/<scene_id>", methods=["DELETE"])
def delete_scene(scene_id):
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.scene_service import SceneService
        SceneService().delete_scene(project_id, scene_id)
        return jsonify({"success": True})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/scenes/<chapter_id>/reorder", methods=["POST"])
def reorder_scenes(chapter_id):
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id", "")
        scene_ids = data.get("scene_ids", [])
        from ..services.writer_agent.scene_service import SceneService
        SceneService().reorder_scenes(project_id, chapter_id, scene_ids)
        return jsonify({"success": True})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/scenes/<chapter_id>/compile", methods=["POST"])
def compile_chapter_from_scenes(chapter_id):
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id", "")
        from ..services.writer_agent.scene_service import SceneService
        result = SceneService().compile_chapter(project_id, chapter_id)
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)


# ---- Preset CRUD ----

@writer_agent_bp.route("/presets", methods=["GET"])
def list_presets():
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.preset_service import PresetService
        presets = PresetService().list_presets(project_id)
        return jsonify({"success": True, "data": presets})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/presets", methods=["POST"])
def create_preset():
    try:
        data = request.get_json() or {}
        from ..services.writer_agent.preset_service import PresetService
        result = PresetService().create_preset(
            project_id=data.get("project_id"),
            name=data["name"],
            system_prompt=data["system_prompt"],
            description=data.get("description", ""),
            is_default=data.get("is_default", 0),
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/presets/<preset_id>", methods=["PUT"])
def update_preset(preset_id):
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id", "")
        from ..services.writer_agent.preset_service import PresetService
        result = PresetService().update_preset(project_id, preset_id, **{
            k: v for k, v in data.items() if k in ("name", "system_prompt", "description", "is_default")
        })
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/presets/<preset_id>", methods=["DELETE"])
def delete_preset(preset_id):
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.preset_service import PresetService
        PresetService().delete_preset(project_id, preset_id)
        return jsonify({"success": True})
    except Exception as exc:
        return _error_response(exc)


# ---- Chapter CRUD ----

@writer_agent_bp.route("/chapters/<project_id>", methods=["GET"])
def list_chapters(project_id):
    try:
        from ..services.writer_agent.chapter_service import ChapterService
        chapters = ChapterService().list_chapters(project_id)
        return jsonify({"success": True, "data": chapters})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/chapters/<project_id>", methods=["POST"])
def create_chapter(project_id):
    try:
        data = request.get_json() or {}
        from ..services.writer_agent.chapter_service import ChapterService
        result = ChapterService().create_chapter(
            project_id,
            title=data.get("title", ""),
            chapter_order=data.get("chapter_order"),
        )
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/chapters/detail/<chapter_id>", methods=["PUT"])
def update_chapter(chapter_id):
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id", "")
        from ..services.writer_agent.chapter_service import ChapterService
        result = ChapterService().update_chapter(project_id, chapter_id, **{
            k: v for k, v in data.items()
            if k in ("title", "summary", "outline_json", "timeline_note", "open_threads_json", "pov_character")
        })
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)


@writer_agent_bp.route("/chapters/detail/<chapter_id>", methods=["DELETE"])
def delete_chapter(chapter_id):
    try:
        project_id = request.args.get("project_id", "")
        from ..services.writer_agent.chapter_service import ChapterService
        ChapterService().delete_chapter(project_id, chapter_id)
        return jsonify({"success": True})
    except Exception as exc:
        return _error_response(exc)


# ---- Migration ----

@writer_agent_bp.route("/migrate/<project_id>", methods=["POST"])
def migrate_project(project_id):
    try:
        from ..services.writer_agent.novel_db_migration import migrate_project as do_migrate
        result = do_migrate(project_id)
        return jsonify({"success": True, "data": result})
    except Exception as exc:
        return _error_response(exc)
