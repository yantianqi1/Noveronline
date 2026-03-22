"""种子任务进度与时间轴记录。"""

from __future__ import annotations

import copy
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from ..models.task import TaskManager, TaskStatus
from .llm_router import LlmRouter


DEFAULT_METRICS = {
    "chapter_count": 0,
    "block_count": 0,
    "completed_blocks": 0,
    "total_blocks": 0,
    "active_workers": 0,
}


class SeedTaskProgressTracker:
    """为种子分析任务维护结构化进度详情。"""

    def __init__(
        self,
        task_manager: TaskManager,
        task_id: str,
        use_llm: bool,
        llm_router: Optional[LlmRouter] = None,
    ):
        self.task_manager = task_manager
        self.task_id = task_id
        self.use_llm = use_llm
        self.llm_router = llm_router or LlmRouter()
        self._initialize_detail()

    def enter_stage(self, stage: str, label: str, progress: int, detail: str = "") -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            self._close_active_stage_event(progress_detail)
            progress_detail["stage"] = stage
            progress_detail["stage_label"] = label
            progress_detail["active_stage"] = self._active_stage(stage, label, progress, "processing")
            progress_detail["llm_activity"] = self._pending_activity(label, stage)
            progress_detail["timeline"].append(self._event(stage, "info", "active", label, detail, {"kind": "stage"}))
            task.status = TaskStatus.PROCESSING
            task.progress = progress
            task.message = label
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def set_counts(self, chapter_count: Optional[int] = None, block_count: Optional[int] = None) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            metrics = progress_detail["task_metrics"]
            if chapter_count is not None:
                metrics["chapter_count"] = chapter_count
            if block_count is not None:
                metrics["block_count"] = block_count
                metrics["total_blocks"] = block_count
                metrics["completed_blocks"] = 0
                metrics["active_workers"] = 0
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def reset_block_progress(self) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            metrics = progress_detail["task_metrics"]
            metrics["completed_blocks"] = 0
            metrics["active_workers"] = 0
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def block_started(self, stage: str, title: str, detail: str, meta: Dict[str, Any]) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            progress_detail["task_metrics"]["active_workers"] += 1
            progress_detail["timeline"].append(self._event(stage, "info", "active", title, detail, meta))
            progress_detail["llm_activity"] = self._activity_snapshot(title, {"stage": stage, **meta})
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def block_completed(self, stage: str, title: str, detail: str, meta: Dict[str, Any]) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            metrics = progress_detail["task_metrics"]
            metrics["active_workers"] = max(0, metrics["active_workers"] - 1)
            metrics["completed_blocks"] += 1
            self._close_matching_block_event(progress_detail, meta.get("block_id"))
            progress_detail["timeline"].append(self._event(stage, "success", "completed", title, detail, meta))
            progress_detail["llm_activity"] = self._pending_activity(progress_detail["stage_label"], stage)
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def note(self, stage: str, title: str, detail: str = "", level: str = "info", meta: Optional[Dict[str, Any]] = None) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            progress_detail["timeline"].append(self._event(stage, level, "completed", title, detail, meta or {}))
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def llm_action(
        self,
        action: str,
        target_type: str = "",
        target_label: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            activity = self._activity_snapshot(
                action,
                {
                    "stage": progress_detail["stage"],
                    "target_type": target_type,
                    "target_label": target_label,
                    **(meta or {}),
                },
            )
            progress_detail["llm_activity"] = activity
            progress_detail["timeline"].append(
                self._event(progress_detail["stage"], "info", "completed", action, target_label, {"kind": "llm", **(meta or {})})
            )
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def complete(self, message: str, result: Dict[str, Any]) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            self._close_active_stage_event(progress_detail)
            progress_detail["active_stage"] = self._active_stage("completed", "全部产物已生成", 100, "completed")
            progress_detail["llm_activity"] = self._done_activity()
            progress_detail["timeline"].append(
                self._event("completed", "success", "completed", "第一阶段分析完成", message, {"kind": "task"})
            )
            task.status = TaskStatus.COMPLETED
            task.progress = 100
            task.message = message
            task.result = result
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def fail(self, error_message: str) -> None:
        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            self._close_active_stage_event(progress_detail)
            progress_detail["active_stage"] = self._active_stage("failed", "任务失败", task.progress, "failed")
            progress_detail["llm_activity"] = self._failed_activity(error_message)
            progress_detail["timeline"].append(
                self._event(progress_detail["stage"], "error", "failed", "第一阶段分析失败", error_message, {"kind": "task"})
            )
            task.status = TaskStatus.FAILED
            task.message = "任务失败"
            task.error = error_message
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)

    def _initialize_detail(self) -> None:
        def mutate(task) -> None:
            task.progress_detail = {
                "stage": "queued",
                "stage_label": "任务已创建，等待开始",
                "active_stage": self._active_stage("queued", "任务已创建，等待开始", 0, "pending"),
                "task_metrics": copy.deepcopy(DEFAULT_METRICS),
                "llm_activity": self._pending_activity("等待进入分析阶段"),
                "timeline": [],
            }

        self.task_manager.mutate_task(self.task_id, mutate)

    def _activity_snapshot(self, action: str, meta: Dict[str, Any]) -> Dict[str, Any]:
        stage = meta.get("stage", "")
        return {
            "enabled": self.use_llm,
            "mode": "llm" if self.use_llm else "offline",
            "model": self._model_name(stage),
            "action": action,
            "target_type": meta.get("target_type", "block" if meta.get("block_id") else ""),
            "target_label": meta.get("target_label", meta.get("block_id", "")),
        }

    def _pending_activity(self, action: str, stage: str = "") -> Dict[str, Any]:
        mode = "llm" if self.use_llm else "offline"
        model = self._model_name(stage)
        return {
            "enabled": self.use_llm,
            "mode": mode,
            "model": model,
            "action": action if self.use_llm else "当前使用规则分析",
            "target_type": "",
            "target_label": "",
        }

    def _done_activity(self) -> Dict[str, Any]:
        mode = "llm" if self.use_llm else "offline"
        return {
            "enabled": self.use_llm,
            "mode": mode,
            "model": self._model_name("ontology"),
            "action": "已完成全部分析",
            "target_type": "",
            "target_label": "",
        }

    def _failed_activity(self, error_message: str) -> Dict[str, Any]:
        activity = self._done_activity()
        activity["action"] = error_message
        return activity

    def _detail_copy(self, detail: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if not detail:
            return {
                "stage": "",
                "stage_label": "",
                "active_stage": self._active_stage("", "", 0, "pending"),
                "task_metrics": copy.deepcopy(DEFAULT_METRICS),
                "llm_activity": self._pending_activity("等待进入分析阶段"),
                "timeline": [],
            }
        payload = copy.deepcopy(detail)
        payload.setdefault("timeline", [])
        payload.setdefault("task_metrics", copy.deepcopy(DEFAULT_METRICS))
        payload.setdefault("llm_activity", self._pending_activity("等待进入分析阶段"))
        payload.setdefault("active_stage", self._active_stage("", "", 0, "pending"))
        return payload

    def _model_name(self, stage: str) -> str:
        if not self.use_llm or not stage:
            return ""
        try:
            return self.llm_router.model_name_for_stage(stage)
        except ValueError:
            return ""

    def _close_active_stage_event(self, progress_detail: Dict[str, Any]) -> None:
        for item in reversed(progress_detail["timeline"]):
            if item.get("status") == "active" and item.get("meta", {}).get("kind") == "stage":
                item["status"] = "completed"
                return

    def _close_matching_block_event(self, progress_detail: Dict[str, Any], block_id: str) -> None:
        for item in reversed(progress_detail["timeline"]):
            if item.get("status") != "active":
                continue
            if item.get("meta", {}).get("block_id") != block_id:
                continue
            item["status"] = "completed"
            return

    def _active_stage(self, key: str, label: str, progress: int, status: str) -> Dict[str, Any]:
        return {
            "key": key,
            "label": label,
            "progress": progress,
            "status": status,
        }

    def _event(
        self,
        stage: str,
        level: str,
        status: str,
        title: str,
        detail: str,
        meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "stage": stage,
            "level": level,
            "status": status,
            "title": title,
            "detail": detail,
            "meta": meta,
        }
