"""步骤级 trace 基础设施单元测试。"""

from __future__ import annotations

import json
import os
import shutil
import threading
import time
import uuid

import pytest

from app.services.step_trace_context import (
    StepTraceContext,
    enter_step,
    get_current_step,
    new_step_id,
    record_call,
)
from app.services.step_trace_writer import load_step_bundle, write_step_bundle
from app.services.seed_pipeline_chapters import (
    PIPELINE_CHAPTERS,
    STAGE_TO_CHAPTER,
    chapter_for_stage,
    label_for_chapter,
)


# ── Pipeline chapters ──


class TestPipelineChapters:
    def test_all_stages_mapped(self):
        all_stages = [s for ch in PIPELINE_CHAPTERS for s in ch["stages"]]
        assert len(all_stages) == len(set(all_stages)), "重复 stage"
        for s in all_stages:
            assert s in STAGE_TO_CHAPTER

    def test_chapter_for_stage(self):
        assert chapter_for_stage("extract_text") == "text_prep"
        assert chapter_for_stage("anchor_generation") == "world_scan"
        assert chapter_for_stage("entity_resolution") == "fact_extract"
        assert chapter_for_stage("ontology") == "output_settle"
        assert chapter_for_stage("nonexistent") == ""

    def test_label_for_chapter(self):
        assert label_for_chapter("text_prep") == "文本准备"
        assert label_for_chapter("output_settle") == "成果沉淀"
        assert label_for_chapter("unknown") == ""


# ── Step trace context ──


class TestStepTraceContext:
    def test_enter_and_exit(self):
        assert get_current_step() is None
        step_id = new_step_id()
        with enter_step(step_id, "test", "grp", "grp_label", "stage", "title") as ctx:
            assert get_current_step() is ctx
            assert ctx.step_id == step_id
            assert ctx.step_kind == "test"
        assert get_current_step() is None

    def test_record_call(self):
        step_id = new_step_id()
        with enter_step(step_id, "test", "g", "gl", "s", "t") as ctx:
            record_call({"call_id": "c1", "model": "gpt-4o"})
            record_call({"call_id": "c2", "model": "gpt-4o"})
            assert ctx.call_count == 2
            assert ctx.calls[0]["call_id"] == "c1"
            assert ctx.calls[1]["call_id"] == "c2"

    def test_record_call_outside_context(self):
        # 不应抛异常
        record_call({"call_id": "orphan"})
        assert get_current_step() is None

    def test_thread_isolation(self):
        """不同线程的 step context 互不干扰。"""
        results = {}

        def worker(name):
            sid = new_step_id()
            with enter_step(sid, "w", "g", "gl", "s", name) as ctx:
                time.sleep(0.01)
                record_call({"call_id": name})
                results[name] = (ctx.step_id, ctx.call_count)

        t1 = threading.Thread(target=worker, args=("A",))
        t2 = threading.Thread(target=worker, args=("B",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert results["A"][1] == 1
        assert results["B"][1] == 1
        assert results["A"][0] != results["B"][0]

    def test_elapsed_ms(self):
        sid = new_step_id()
        with enter_step(sid, "t", "g", "gl", "s", "t") as ctx:
            time.sleep(0.05)
            assert ctx.elapsed_ms >= 40  # 至少 40ms

    def test_new_step_id_format(self):
        sid = new_step_id()
        assert sid.startswith("step_")
        assert len(sid) == 17  # "step_" + 12 hex chars


# ── Step trace writer ──


TRACE_BASE = os.path.join(os.path.dirname(__file__), "_test_trace_tmp")


@pytest.fixture(autouse=True)
def _clean_trace_dir():
    yield
    if os.path.exists(TRACE_BASE):
        shutil.rmtree(TRACE_BASE)


class TestStepTraceWriter:
    def _override_upload_folder(self, monkeypatch):
        monkeypatch.setattr("app.services.step_trace_writer.Config.UPLOAD_FOLDER", TRACE_BASE)

    def test_write_and_load(self, monkeypatch):
        self._override_upload_folder(monkeypatch)
        bundle = {
            "step_id": "step_abc123",
            "title": "测试步骤",
            "stage": "extract_text",
            "calls": [{"call_id": "c1", "model": "test"}],
        }
        write_step_bundle("proj1", "task1", "step_abc123", bundle)
        loaded = load_step_bundle("proj1", "task1", "step_abc123")
        assert loaded is not None
        assert loaded["step_id"] == "step_abc123"
        assert len(loaded["calls"]) == 1

    def test_load_nonexistent(self, monkeypatch):
        self._override_upload_folder(monkeypatch)
        assert load_step_bundle("proj_none", "task_none", "step_none") is None

    def test_overwrite(self, monkeypatch):
        self._override_upload_folder(monkeypatch)
        write_step_bundle("p", "t", "s1", {"v": 1})
        write_step_bundle("p", "t", "s1", {"v": 2})
        loaded = load_step_bundle("p", "t", "s1")
        assert loaded["v"] == 2


# ── Progress tracker step integration ──


class TestProgressTrackerSteps:
    """集成测试：SeedTaskProgressTracker 的 begin_step/end_step。"""

    def test_begin_end_step_paired(self, monkeypatch, tmp_path):
        from app.config import Config
        from app.models.task import TaskManager

        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
        TaskManager._instance = None

        tm = TaskManager()
        task_id = tm.create_task(task_type="test", metadata={"project_id": "p1"})

        from app.services.seed_task_progress import SeedTaskProgressTracker

        tracker = SeedTaskProgressTracker(tm, task_id, use_llm=False, project_id="p1")
        tracker.enter_stage("extract_text", "文本提取", 5)

        sid = tracker.begin_step("extract_text", "file_extract", "提取文本")
        assert sid.startswith("step_")
        # 此时应有 active step context
        assert get_current_step() is not None

        tracker.end_step(sid)
        # 退出后 context 清空
        assert get_current_step() is None

        # 检查 timeline 事件
        task = tm.get_task(task_id)
        timeline = task.progress_detail.get("timeline", [])
        step_events = [e for e in timeline if e.get("meta", {}).get("step_id") == sid]
        assert len(step_events) >= 2  # start + complete
        complete_event = [e for e in step_events if e["status"] == "completed"]
        assert len(complete_event) >= 1
        meta = complete_event[-1]["meta"]
        assert "elapsed_ms" in meta
        assert "llm_call_count" in meta
        assert meta["group_key"] == "text_prep"

        TaskManager._instance = None

    def test_note_gets_step_id(self, monkeypatch, tmp_path):
        from app.config import Config
        from app.models.task import TaskManager
        from app.services.seed_task_progress import SeedTaskProgressTracker

        monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path / "uploads"))
        TaskManager._instance = None

        tm = TaskManager()
        task_id = tm.create_task(task_type="test", metadata={})
        tracker = SeedTaskProgressTracker(tm, task_id, use_llm=False)
        tracker.enter_stage("extract_text", "文本提取", 5)
        tracker.note("extract_text", "文本提取完成", "3份文稿")

        task = tm.get_task(task_id)
        timeline = task.progress_detail.get("timeline", [])
        note_events = [e for e in timeline if e["title"] == "文本提取完成"]
        assert len(note_events) == 1
        assert note_events[0]["meta"].get("step_id", "").startswith("step_")

        TaskManager._instance = None
