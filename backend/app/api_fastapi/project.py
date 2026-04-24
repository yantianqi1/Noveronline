"""Native FastAPI project and seed routes."""

from __future__ import annotations

import os
from datetime import datetime

from fastapi import APIRouter, File, Form, UploadFile

from app.config import Config
from app.models.project import ProjectManager, ProjectStatus
from app.models.task import TaskManager
from app.services.project_deletion_service import cascade_delete_project
from app.services.seed_extract_task_service import SeedExtractTaskService
from app.services.step_trace_writer import load_step_bundle

from app.schemas.project_schemas import BuildGraphRequest, RerunSeedRequest
from app.schemas.graph_generation_schemas import GraphBondGenerateRequest

from .common import err, no_store, ok

router = APIRouter(prefix="/project", tags=["project"])

SEED_TASK_RECOVERY_ERROR = "种子分析任务已中断，服务可能已重启，请重新上传并重试。"
GRAPH_TASK_RECOVERY_ERROR = "图谱构建任务已中断，服务可能已重启，请重新发起构建。"


class UploadFileStorageAdapter:
    def __init__(self, upload: UploadFile):
        self.filename = upload.filename or ""
        self._upload = upload

    def save(self, path: str) -> None:
        self._upload.file.seek(0)
        with open(path, "wb") as file_obj:
            file_obj.write(self._upload.file.read())


def allowed_file(filename: str) -> bool:
    if not filename or "." not in filename:
        return False
    return os.path.splitext(filename)[1].lower().lstrip(".") in Config.ALLOWED_EXTENSIONS


async def reconcile_project_task_state(project, task_manager=None):
    if not project:
        return None
    manager = task_manager or TaskManager()
    if await _is_missing_seed_task(project, manager):
        return _mark_project_failed(project, "seed_task_id", SEED_TASK_RECOVERY_ERROR)
    if await _is_missing_graph_task(project, manager):
        return _mark_project_failed(project, "graph_build_task_id", GRAPH_TASK_RECOVERY_ERROR)
    return project


async def _is_missing_seed_task(project, task_manager) -> bool:
    return project.status == ProjectStatus.SEED_PROCESSING and bool(project.seed_task_id) and await task_manager.get_task(project.seed_task_id) is None


async def _is_missing_graph_task(project, task_manager) -> bool:
    return project.status == ProjectStatus.GRAPH_BUILDING and bool(project.graph_build_task_id) and await task_manager.get_task(project.graph_build_task_id) is None


def _mark_project_failed(project, task_field: str, error_message: str):
    project.status = ProjectStatus.FAILED
    project.error = error_message
    setattr(project, task_field, None)
    ProjectManager.save_project(project)
    return project


async def _recovered_task(task_id: str):
    project = ProjectManager.find_project_by_task_id(task_id)
    if not project:
        return None
    timestamp = datetime.now().isoformat()
    if task_id == project.seed_task_id:
        await reconcile_project_task_state(project)
        return _task_payload(task_id, "seed_extract", SEED_TASK_RECOVERY_ERROR, timestamp)
    if task_id == project.graph_build_task_id:
        await reconcile_project_task_state(project)
        return _task_payload(task_id, "graph_build", GRAPH_TASK_RECOVERY_ERROR, timestamp)
    return None


def _task_payload(task_id: str, task_type: str, error_message: str, timestamp: str) -> dict:
    return {
        "task_id": task_id, "task_type": task_type, "status": "failed",
        "created_at": timestamp, "updated_at": timestamp, "progress": 0,
        "message": "任务失败", "progress_detail": {}, "result": None,
        "error": error_message, "metadata": {},
    }


@router.post("/seed/extract")
async def extract_story_seed(
    analysis_goal: str = Form(""),
    project_name: str = Form("Untitled Novel Project"),
    additional_context: str = Form(""),
    segment_token_limit: int = Form(50000),
    use_llm: str = Form("true"),
    files: list[UploadFile] = File(...),
):
    try:
        if not analysis_goal.strip():
            return err("请提供 analysis_goal", status_code=400)
        if use_llm.strip().lower() in {"0", "false", "no", "off"}:
            return err("POST /api/project/seed/extract 仅支持 LLM 模式；离线分析请直接调用 SeedExtractTaskService。", status_code=400)
        uploads = [item for item in files if item.filename and allowed_file(item.filename)]
        if not uploads:
            return err("请至少上传一个文件", status_code=400)
        project = ProjectManager.create_project(name=project_name.strip() or "Untitled Novel Project")
        project.analysis_goal = analysis_goal.strip()
        saved_count = _save_uploads(project, uploads)
        if not saved_count:
            ProjectManager.delete_project(project.project_id)
            return err("没有成功处理任何文档", status_code=400)
        ProjectManager.save_project(project)
        task_id = await SeedExtractTaskService().create_task(
            project.project_id, project.name, project.analysis_goal,
            additional_context.strip(), True, segment_token_limit,
        )
        return ok({
            "project_id": project.project_id, "project_name": project.name,
            "analysis_goal": project.analysis_goal, "task_id": task_id,
            "status": "processing", "message": "文件已保存，后台正在切分章节并生成种子分析。",
            "files": project.files,
        }, status_code=202)
    except Exception as exc:
        return err(exc)


def _save_uploads(project, uploads: list[UploadFile]) -> int:
    saved_count = 0
    for upload in uploads:
        file_info = ProjectManager.save_file_to_project(
            project.project_id, UploadFileStorageAdapter(upload), upload.filename or "",
        )
        project.files.append({
            "filename": file_info["original_filename"],
            "saved_filename": file_info["saved_filename"],
            "size": file_info["size"],
        })
        saved_count += 1
    return saved_count


@router.post("/seed/rerun/{project_id}")
async def rerun_seed_pipeline(project_id: str, body: RerunSeedRequest | None = None):
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return err(f"项目不存在: {project_id}", status_code=404)
        if not project.files:
            return err("项目没有已上传的文件", status_code=400)
        data = body.model_dump() if body else {}
        task_id = await SeedExtractTaskService().create_task(
            project.project_id, project.name,
            data.get("analysis_goal", project.analysis_goal or "提取全部有名角色、组织和关系"),
            data.get("additional_context", ""), True, int(data.get("segment_token_limit", 50000)),
        )
        return ok({"project_id": project.project_id, "task_id": task_id, "status": "processing", "message": "正在使用已有文件重新运行种子管线。"}, status_code=202)
    except Exception as exc:
        return err(exc)


@router.post("/seed/retry-failed-segments/{project_id}")
async def retry_failed_segments(project_id: str):
    """手动重读 reading_notes.json 中仍标记为 retry_needed 的段落。"""
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return err(f"项目不存在: {project_id}", status_code=404)
        task_id = await SeedExtractTaskService().create_retry_task(project.project_id)
        return ok(
            {
                "project_id": project.project_id,
                "task_id": task_id,
                "status": "processing",
                "message": "正在重读失败段落。",
            },
            status_code=202,
        )
    except Exception as exc:
        return err(exc)


@router.post("/{project_id}/relink-data")
async def relink_project_data(project_id: str):
    """重新打通数据：再跑一次档案同步 / 图谱构建 / FTS 重建。"""
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return err(f"项目不存在: {project_id}", status_code=404)
        if project.seed_task_id:
            return err(
                "当前有进行中的种子或打通任务，请等它结束后再试。",
                status_code=409,
            )
        task_id = await SeedExtractTaskService().create_relink_task(project.project_id)
        return ok(
            {
                "project_id": project.project_id,
                "task_id": task_id,
                "status": "processing",
                "message": "正在重新打通档案库 / 图谱 / 全局索引。",
            },
            status_code=202,
        )
    except Exception as exc:
        return err(exc)


@router.post("/build-graph")
async def build_story_graph(body: BuildGraphRequest):
    try:
        payload = body.model_dump()
        project_id = payload.get("project_id")
        if not project_id:
            return err("请提供 project_id", status_code=400)
        project = ProjectManager.get_project(project_id)
        if not project:
            return err(f"项目不存在: {project_id}", status_code=404)
        extracted_text = ProjectManager.get_extracted_text(project_id)
        if not extracted_text:
            return err("项目缺少提取文本", status_code=400)
        if not project.ontology:
            return err("项目尚未生成 ontology", status_code=400)
        from app.services.graph_builder import GraphBuilderService
        task_id = await GraphBuilderService().build_graph_async(
            project_id=project_id, text=extracted_text,
            ontology=project.ontology, graph_name=payload.get("graph_name", "Novel Story Graph"),
            chunk_size=project.chunk_size, chunk_overlap=project.chunk_overlap,
        )
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        project.error = None
        ProjectManager.save_project(project)
        return ok({"project_id": project_id, "task_id": task_id, "status": "graph_building"})
    except Exception as exc:
        return err(exc)


@router.get("/task/{task_id}")
async def get_project_task(task_id: str):
    task = await TaskManager().get_task(task_id)
    if not task:
        recovered = await _recovered_task(task_id)
        if recovered:
            return no_store({"success": True, "data": recovered})
        return no_store({"success": False, "error": f"任务不存在: {task_id}"}, status_code=404)
    task_dict = task.to_dict()
    _sync_project_from_task(task_id, task_dict)
    return no_store({"success": True, "data": task_dict})


def _sync_project_from_task(task_id: str, task_dict: dict) -> None:
    if task_dict["status"] not in {"completed", "failed"}:
        return
    for project in ProjectManager.list_projects(limit=500):
        if project.graph_build_task_id != task_id:
            continue
        if task_dict["status"] == "completed" and (task_dict.get("result") or {}).get("graph_id"):
            project.graph_id = task_dict["result"]["graph_id"]
            project.status = ProjectStatus.GRAPH_COMPLETED
            project.error = None
        elif task_dict["status"] == "failed":
            project.status = ProjectStatus.FAILED
            project.error = task_dict.get("error") or "图谱构建失败"
        ProjectManager.save_project(project)
        return


@router.post("/task/{task_id}/cancel")
async def cancel_task(task_id: str):
    success = await TaskManager().cancel_task(task_id)
    if not success:
        task = await TaskManager().get_task(task_id)
        status = task.status.value if task else "not_found"
        return err(f"无法取消任务（当前状态: {status}）", status_code=400)
    return ok({"task_id": task_id, "status": "cancelled"})


@router.get("/task/{task_id}/steps/{step_id}/trace")
async def get_step_trace(task_id: str, step_id: str):
    task = await TaskManager().get_task(task_id)
    if not task:
        return no_store({"success": False, "error": "任务不存在"}, status_code=404)
    project_id = (task.metadata or {}).get("project_id", "")
    bundle = load_step_bundle(project_id, task_id, step_id) if project_id else None
    if bundle is None:
        return no_store({"success": False, "error": "trace_unavailable"}, status_code=404)
    return no_store({"success": True, "data": bundle})


@router.get("/list")
async def list_projects(limit: int = 50):
    manager = TaskManager()
    projects = [await reconcile_project_task_state(project, manager) for project in ProjectManager.list_projects(limit=limit)]
    return ok([project.to_dict() for project in projects], count=len(projects))


@router.get("/{project_id}/graph")
async def get_project_graph(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return err(f"项目不存在: {project_id}", status_code=404)
    from app.database import get_engine
    from app.repositories.graph_repo import GraphRepository

    repo = GraphRepository(get_engine())
    if not repo.has_graph(project_id):
        return err("该项目尚未生成本地图谱", status_code=404)
    meta = repo.load_snapshot(project_id) or {}
    nodes = repo.load_all_nodes(project_id)
    edges = repo.load_all_edges(project_id)
    data = {
        **meta,
        "nodes": nodes,
        "edges": edges,
        "node_count": len(nodes),
        "edge_count": len(edges),
    }
    return ok(data)


@router.post("/{project_id}/graph/generate-bond")
async def generate_graph_bond(project_id: str, body: GraphBondGenerateRequest):
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return err(f"项目不存在: {project_id}", status_code=404)

        from app.database import get_engine
        from app.services.graph_bond_generator import GraphBondGenerator
        from app.services.llm_router import LlmRouter

        generator = GraphBondGenerator(get_engine(), LlmRouter())
        result = generator.run(
            project_id=project_id,
            node_uuids=body.node_uuids,
            generate_bonds=body.generate_bonds,
            generate_threads=body.generate_threads,
        )
        return ok(result)
    except ValueError as exc:
        return err(str(exc), status_code=400)
    except Exception as exc:
        return err(exc)


@router.get("/{project_id}")
async def get_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return err(f"项目不存在: {project_id}", status_code=404)
    return ok((await reconcile_project_task_state(project)).to_dict())


@router.delete("/{project_id}")
async def delete_project(project_id: str):
    project = ProjectManager.get_project(project_id)
    if not project:
        return err(f"项目不存在: {project_id}", status_code=404)
    cleanup_stats = cascade_delete_project(project_id)
    ProjectManager.delete_project(project_id)
    return ok({
        "project_id": project_id,
        "name": project.name,
        "deleted": True,
        "cleanup_stats": cleanup_stats,
    })
