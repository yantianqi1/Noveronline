"""项目与小说种子管理 API"""

import os
import traceback
from datetime import datetime

from flask import jsonify, request

from . import project_bp
from ..config import Config
from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskManager
from ..services.seed_extract_task_service import SeedExtractTaskService

SEED_TASK_RECOVERY_ERROR = "种子分析任务已中断，服务可能已重启，请重新上传并重试。"
GRAPH_TASK_RECOVERY_ERROR = "图谱构建任务已中断，服务可能已重启，请重新发起构建。"


def allowed_file(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip(".")
    return ext in Config.ALLOWED_EXTENSIONS


def form_bool(field_name: str, default: bool) -> bool:
    raw_value = request.form.get(field_name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def reconcile_project_task_state(project, task_manager=None):
    if not project:
        return None
    manager = task_manager or TaskManager()
    if _is_missing_seed_task(project, manager):
        return _mark_project_failed(project, "seed_task_id", SEED_TASK_RECOVERY_ERROR)
    if _is_missing_graph_task(project, manager):
        return _mark_project_failed(project, "graph_build_task_id", GRAPH_TASK_RECOVERY_ERROR)
    return project


def _is_missing_seed_task(project, task_manager) -> bool:
    return (
        project.status == ProjectStatus.SEED_PROCESSING
        and bool(project.seed_task_id)
        and task_manager.get_task(project.seed_task_id) is None
    )


def _is_missing_graph_task(project, task_manager) -> bool:
    return (
        project.status == ProjectStatus.GRAPH_BUILDING
        and bool(project.graph_build_task_id)
        and task_manager.get_task(project.graph_build_task_id) is None
    )


def _mark_project_failed(project, task_field: str, error_message: str):
    project.status = ProjectStatus.FAILED
    project.error = error_message
    setattr(project, task_field, None)
    ProjectManager.save_project(project)
    return project


def build_recovered_task_payload(task_id: str, task_type: str, error_message: str, timestamp: str):
    return {
        "task_id": task_id,
        "task_type": task_type,
        "status": "failed",
        "created_at": timestamp,
        "updated_at": timestamp,
        "progress": 0,
        "message": "任务失败",
        "progress_detail": {},
        "result": None,
        "error": error_message,
        "metadata": {},
    }


def no_store_json(payload, status: int = 200):
    response = jsonify(payload)
    response.headers["Cache-Control"] = "no-store"
    response.status_code = status
    return response


def recover_missing_task(task_id: str):
    project = ProjectManager.find_project_by_task_id(task_id)
    if not project:
        return None
    timestamp = datetime.now().isoformat()
    if task_id == project.seed_task_id:
        reconcile_project_task_state(project)
        return build_recovered_task_payload(task_id, "seed_extract", SEED_TASK_RECOVERY_ERROR, timestamp)
    if task_id == project.graph_build_task_id:
        reconcile_project_task_state(project)
        return build_recovered_task_payload(task_id, "graph_build", GRAPH_TASK_RECOVERY_ERROR, timestamp)
    return None


@project_bp.route("/seed/extract", methods=["POST"])
def extract_story_seed():
    try:
        analysis_goal = request.form.get("analysis_goal", "").strip()
        project_name = request.form.get("project_name", "Untitled Novel Project").strip()
        additional_context = request.form.get("additional_context", "").strip()
        use_llm = form_bool("use_llm", True)

        if not analysis_goal:
            return jsonify({"success": False, "error": "请提供 analysis_goal"}), 400
        if not use_llm:
            return jsonify({
                "success": False,
                "error": "POST /api/project/seed/extract 仅支持 LLM 模式；请移除 use_llm=false，并先在全局设施面板完成所需模块绑定。",
            }), 400

        uploaded_files = request.files.getlist("files")
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({"success": False, "error": "请至少上传一个文件"}), 400

        project = ProjectManager.create_project(name=project_name)
        project.analysis_goal = analysis_goal
        saved_files = _save_project_uploads(project, uploaded_files)
        if not saved_files:
            ProjectManager.delete_project(project.project_id)
            return jsonify({"success": False, "error": "没有成功处理任何文档"}), 400
        ProjectManager.save_project(project)
        task_id = SeedExtractTaskService().create_task(
            project_id=project.project_id,
            project_name=project.name,
            analysis_goal=analysis_goal,
            additional_context=additional_context,
            use_llm=use_llm,
        )
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "analysis_goal": project.analysis_goal,
                "task_id": task_id,
                "status": "processing",
                "message": "文件已保存，后台正在切分章节并生成种子分析。",
                "files": project.files,
            },
        }), 202
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


def _save_project_uploads(project, uploaded_files) -> int:
    saved_count = 0
    for file in uploaded_files:
        if not file or not file.filename or not allowed_file(file.filename):
            continue
        file_info = ProjectManager.save_file_to_project(project.project_id, file, file.filename)
        project.files.append({
            "filename": file_info["original_filename"],
            "saved_filename": file_info["saved_filename"],
            "size": file_info["size"],
        })
        saved_count += 1
    return saved_count


@project_bp.route("/build-graph", methods=["POST"])
def build_story_graph():
    try:
        data = request.get_json() or {}
        project_id = data.get("project_id")
        graph_name = data.get("graph_name", "Novel Story Graph")

        if not project_id:
            return jsonify({"success": False, "error": "请提供 project_id"}), 400

        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404

        extracted_text = ProjectManager.get_extracted_text(project_id)
        if not extracted_text:
            return jsonify({"success": False, "error": "项目缺少提取文本"}), 400

        if not project.ontology:
            return jsonify({"success": False, "error": "项目尚未生成 ontology"}), 400

        from ..services.graph_builder import GraphBuilderService

        builder = GraphBuilderService()
        task_id = builder.build_graph_async(
            project_id=project_id,
            text=extracted_text,
            ontology=project.ontology,
            graph_name=graph_name,
            chunk_size=project.chunk_size,
            chunk_overlap=project.chunk_overlap,
        )

        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        project.error = None
        ProjectManager.save_project(project)

        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "status": "graph_building",
            },
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }), 500


@project_bp.route("/task/<task_id>", methods=["GET"])
def get_project_task(task_id: str):
    try:
        task_manager = TaskManager()
        task = task_manager.get_task(task_id)
        if not task:
            recovered = recover_missing_task(task_id)
            if recovered:
                return no_store_json({"success": True, "data": recovered})
            return no_store_json({"success": False, "error": f"任务不存在: {task_id}"}, 404)

        task_dict = task.to_dict()

        if task_dict["status"] == "completed":
            result = task_dict.get("result") or {}
            graph_id = result.get("graph_id")
            if graph_id:
                for project in ProjectManager.list_projects(limit=500):
                    if project.graph_build_task_id == task_id:
                        project.graph_id = graph_id
                        project.status = ProjectStatus.GRAPH_COMPLETED
                        project.error = None
                        ProjectManager.save_project(project)
                        break
        elif task_dict["status"] == "failed":
            for project in ProjectManager.list_projects(limit=500):
                if project.graph_build_task_id == task_id:
                    project.status = ProjectStatus.FAILED
                    project.error = task_dict.get("error") or "图谱构建失败"
                    ProjectManager.save_project(project)
                    break

        return no_store_json({"success": True, "data": task_dict})
    except Exception as e:
        return no_store_json({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc(),
        }, 500)


@project_bp.route("/<project_id>", methods=["GET"])
def get_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404
    project = reconcile_project_task_state(project)
    return jsonify({"success": True, "data": project.to_dict()})


@project_bp.route("/<project_id>", methods=["DELETE"])
def delete_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404
    ProjectManager.delete_project(project_id)
    return jsonify({
        "success": True,
        "data": {
            "project_id": project_id,
            "name": project.name,
            "deleted": True,
        },
    })


@project_bp.route("/list", methods=["GET"])
def list_projects():
    task_manager = TaskManager()
    projects = [
        reconcile_project_task_state(project, task_manager)
        for project in ProjectManager.list_projects(limit=request.args.get("limit", 50, type=int))
    ]
    return jsonify({
        "success": True,
        "data": [project.to_dict() for project in projects],
        "count": len(projects),
    })
