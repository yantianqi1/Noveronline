"""本地图谱构建后台任务逻辑。"""

import traceback
from typing import Any, Dict, List

from ..models.project import ProjectManager, ProjectStatus
from ..models.task import Task, TaskStatus

# 阶段进度区间，仅作为兜底；真实进度以 builder emit 的 progress 为准
_STAGE_FLOOR = {
    "load_artifacts": 10,
    "collect_entities": 28,
    "merge_nodes": 45,
    "build_relationships": 60,
    "build_events": 72,
    "build_artifacts_rules": 85,
    "persist": 92,
    "finalize": 100,
}


def _build_progress_callback(service, task_id: str):
    task_manager = service.task_manager

    def _callback(event: Dict[str, Any]) -> None:
        stage = str(event.get("stage", "")) or "unknown"
        progress = int(event.get("progress") or _STAGE_FLOOR.get(stage, 0))
        progress = max(0, min(100, progress))

        def _mutate(task: Task) -> None:
            stages: List[Dict[str, Any]] = list(task.metadata.get("stages") or [])
            stages.append({
                "stage": stage,
                "progress": progress,
                "counts": event.get("counts") or {},
                "sample": event.get("sample") or [],
                "elapsed_ms": int(event.get("elapsed_ms") or 0),
            })
            task.metadata["stages"] = stages
            task.metadata["latest_stage"] = stage
            task.progress = progress
            task.message = stage  # 前端用 buildStageMeta 翻译

        task_manager.sync_bridge(task_manager.mutate_task(task_id, _mutate))

    return _callback


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
    """Sync worker — expected to run inside ``asyncio.to_thread``."""
    task_manager = service.task_manager
    task_manager.sync_bridge(task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=0,
        message="start",
    ))
    progress_callback = _build_progress_callback(service, task_id)
    try:
        snapshot = service.build_graph(
            project_id=project_id,
            text=text,
            ontology=ontology,
            graph_name=graph_name,
            progress_callback=progress_callback,
        )
        graph_info = service.get_graph_info(snapshot.graph_id)
        _complete_graph_project(project_id, snapshot.graph_id)
        task_manager.sync_bridge(task_manager.complete_task(task_id, {
            "graph_id": snapshot.graph_id,
            "graph_info": graph_info.to_dict(),
            "node_count": snapshot.node_count,
            "edge_count": snapshot.edge_count,
        }))
    except Exception as error:
        error_msg = f"{str(error)}\n{traceback.format_exc()}"
        # 写一条 failed 阶段事件，便于前端定位出错位置
        def _mutate_failed(task: Task) -> None:
            stages: List[Dict[str, Any]] = list(task.metadata.get("stages") or [])
            stages.append({
                "stage": "failed",
                "progress": task.progress,
                "counts": {},
                "sample": [],
                "elapsed_ms": 0,
                "error_summary": str(error).splitlines()[0] if str(error) else "构建失败",
                "traceback": traceback.format_exc(),
                "failed_after": task.metadata.get("latest_stage", ""),
            })
            task.metadata["stages"] = stages
        task_manager.sync_bridge(task_manager.mutate_task(task_id, _mutate_failed))
        _fail_graph_project(project_id, error_msg)
        task_manager.sync_bridge(task_manager.fail_task(task_id, error_msg))


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
