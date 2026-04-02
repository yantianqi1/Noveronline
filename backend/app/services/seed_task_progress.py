"""种子任务进度与时间轴记录。"""

from __future__ import annotations

import copy
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from ..models.task import TaskManager, TaskStatus
from .llm_router import LlmRouter
from .seed_pipeline_chapters import chapter_for_stage, label_for_chapter
from .step_trace_context import StepTraceContext, enter_step, new_step_id
from .step_trace_writer import write_step_bundle

logger = logging.getLogger(__name__)

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
        project_id: str = "",
        llm_router: Optional[LlmRouter] = None,
    ):
        self.task_manager = task_manager
        self.task_id = task_id
        self.project_id = project_id
        self.use_llm = use_llm
        self.llm_router = llm_router or LlmRouter()
        self._active_step_cm: Optional[Any] = None
        self._active_step_ctx: Optional[StepTraceContext] = None
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

    # ── Step lifecycle ──

    def begin_step(
        self,
        stage: str,
        step_kind: str,
        title: str,
        group_key: str = "",
        group_label: str = "",
    ) -> str:
        """进入一个逻辑小步骤，返回 step_id。同时激活 trace 上下文。"""
        if not group_key:
            group_key = chapter_for_stage(stage)
        if not group_label:
            group_label = label_for_chapter(group_key)

        step_id = new_step_id()
        cm = enter_step(step_id, step_kind, group_key, group_label, stage, title)
        ctx = cm.__enter__()
        self._active_step_cm = cm
        self._active_step_ctx = ctx

        step_meta = {
            "kind": step_kind,
            "step_id": step_id,
            "step_kind": step_kind,
            "group_key": group_key,
            "group_label": group_label,
            "has_trace": False,
        }

        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            progress_detail["timeline"].append(
                self._event(stage, "info", "active", title, "", step_meta)
            )
            task.progress_detail = progress_detail

        self.task_manager.mutate_task(self.task_id, mutate)
        return step_id

    def end_step(self, step_id: str) -> None:
        """结束一个逻辑小步骤，写 trace bundle 并发射 complete 事件。"""
        ctx = self._active_step_ctx
        if ctx is None or ctx.step_id != step_id:
            logger.warning("end_step 找不到匹配的 step 上下文: %s", step_id)
            return

        elapsed_ms = ctx.elapsed_ms
        call_count = ctx.call_count
        calls = list(ctx.calls)
        has_trace = call_count > 0

        # 退出 step context
        try:
            self._active_step_cm.__exit__(None, None, None)
        except Exception:
            logger.exception("退出 step context 异常: %s", step_id)
        self._active_step_cm = None
        self._active_step_ctx = None

        # 写 trace bundle
        if has_trace and self.project_id:
            bundle = {
                "step_id": ctx.step_id,
                "title": ctx.title,
                "stage": ctx.stage,
                "group_key": ctx.group_key,
                "group_label": ctx.group_label,
                "started_at": ctx.started_at_wall,
                "completed_at": datetime.now().isoformat(timespec="seconds"),
                "elapsed_ms": elapsed_ms,
                "call_count": call_count,
                "calls": calls,
            }
            write_step_bundle(self.project_id, self.task_id, step_id, bundle)

        step_meta = {
            "kind": ctx.step_kind,
            "step_id": step_id,
            "step_kind": ctx.step_kind,
            "group_key": ctx.group_key,
            "group_label": ctx.group_label,
            "has_trace": has_trace,
            "elapsed_ms": elapsed_ms,
            "llm_call_count": call_count,
        }

        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            # 关闭匹配的 start 事件
            for item in reversed(progress_detail["timeline"]):
                if item.get("status") == "active" and item.get("meta", {}).get("step_id") == step_id:
                    item["status"] = "completed"
                    break
            progress_detail["timeline"].append(
                self._event(ctx.stage, "success", "completed", f"完成 {ctx.title}", "", step_meta)
            )
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
        note_meta = dict(meta or {})
        if "step_id" not in note_meta:
            note_meta["step_id"] = new_step_id()
            note_meta.setdefault("step_kind", note_meta.get("kind", "note"))
            group_key = chapter_for_stage(stage)
            note_meta.setdefault("group_key", group_key)
            note_meta.setdefault("group_label", label_for_chapter(group_key))
            note_meta.setdefault("has_trace", False)

        def mutate(task) -> None:
            progress_detail = self._detail_copy(task.progress_detail)
            progress_detail["timeline"].append(self._event(stage, level, "completed", title, detail, note_meta))
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
