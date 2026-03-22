"""项目图谱查询 API。"""

from flask import jsonify

from . import project_bp
from ..models.project import ProjectManager
from ..services.graph_builder import GraphBuilderService
from ..services.local_story_graph_storage import LocalStoryGraphStorage
from ..services.local_story_graph_support import local_graph_id


@project_bp.route("/<project_id>/graph", methods=["GET"])
def get_project_graph(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return jsonify({"success": False, "error": f"项目不存在: {project_id}"}), 404
    storage = LocalStoryGraphStorage()
    graph_id = project.graph_id or local_graph_id(project_id)
    if not storage.has_graph(project_id):
        return jsonify({"success": False, "error": "该项目尚未生成本地图谱"}), 404
    payload = GraphBuilderService(storage=storage).get_graph_data(graph_id)
    return jsonify({"success": True, "data": payload})
