"""本地图谱构建后台线程逻辑。"""

from typing import Any, Dict

from ..models.project import ProjectManager, ProjectStatus
from ..models.task import TaskStatus


def run_graph_build(
    service,
    task_id: str,
    project_id: str,
    text: str,
    ontology: Dict[str, Any],
    graph_name: str,
    chunk_size: int,
    chunk_overlap: int,
):
    task_manager = service.task_manager
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=5,
        message="开始本地图谱构建...",
    )
    try:
        task_manager.update_task(
            task_id,
            progress=20,
            message="正在读取项目工件...",
        )
        task_manager.update_task(
            task_id, progress=45, message="正在装配节点、边和证据..."
        )
        snapshot = service.build_graph(
            project_id=project_id,
            text=text,
            ontology=ontology,
            graph_name=graph_name,
        )
        graph_info = service.get_graph_info(snapshot.graph_id)
        service._wait_for_episodes(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            task_id=task_id,
        )
        _complete_graph_project(project_id, snapshot.graph_id)
        task_manager.complete_task(task_id, {
            "graph_id": snapshot.graph_id,
            "graph_info": graph_info.to_dict(),
            "node_count": snapshot.node_count,
            "edge_count": snapshot.edge_count,
        })
    except Exception as error:
        import traceback

        error_msg = f"{str(error)}\n{traceback.format_exc()}"
        _fail_graph_project(project_id, error_msg)
        task_manager.fail_task(task_id, error_msg)


def _complete_graph_project(project_id: str, graph_id: str) -> None:
    project = ProjectManager.get_project(project_id)
    if not project:
        return
    project.graph_id = graph_id
    project.status = ProjectStatus.GRAPH_COMPLETED
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)


def _fail_graph_project(project_id: str, error_message: str) -> None:
    project = ProjectManager.get_project(project_id)
    if not project:
        return
    project.status = ProjectStatus.FAILED
    project.graph_build_task_id = None
    project.error = error_message
    ProjectManager.save_project(project)
