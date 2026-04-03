# Task Cancellation & Enhanced Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add cooperative task cancellation (cancel running seed pipeline from frontend) and per-task file logging with LLM call details for debugging.

**Architecture:** Cancellation uses a `CANCELLED` TaskStatus that the worker thread checks between segments/stages. Logging uses a `TaskFileLogger` that writes structured logs per task to the project directory. Both integrate into the existing SeedExtractRunner → SequentialReader → CharacterAgentProfileGenerator pipeline.

**Tech Stack:** Python 3.11+ / Flask, Vue 3, pytest, existing TaskManager (SQLite-backed singleton)

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/services/task_cancelled.py` | `TaskCancelledException` — raised when cancellation detected |
| `backend/app/utils/task_file_logger.py` | `TaskFileLogger` — per-task log file writer with LLM call logging |
| `backend/tests/test_task_cancellation.py` | Cancellation mechanism tests |
| `backend/tests/test_task_file_logger.py` | Logger tests |

### Modified Files
| File | Changes |
|------|---------|
| `backend/app/models/task.py` | Add `CANCELLED` status, `cancel_task()` method |
| `backend/app/api/project.py` | Add `POST /api/project/task/<task_id>/cancel` endpoint |
| `backend/app/services/sequential_reader.py` | Accept `cancel_check` callback, check between segments |
| `backend/app/services/character_agent_profile_generator.py` | Accept `cancel_check` callback, check before each profile |
| `backend/app/services/seed_extract_runner.py` | Create logger, wire cancel checks, catch `TaskCancelledException` |
| `backend/app/services/seed_extract_task_service.py` | Pass `task_id` / `task_manager` to runner for cancel checks |
| `frontend/src/api/project.js` | Add `cancelTask(taskId)` API function |
| `frontend/src/composables/useSeedUpload.js` | Add `cancelUpload()` method, handle cancelled state |
| `frontend/src/views/overview/SeedUploadFormFields.vue` | Add cancel button with confirmation dialog |

---

## Task 1: TaskCancelledException + TaskStatus.CANCELLED

**Files:**
- Create: `backend/app/services/task_cancelled.py`
- Modify: `backend/app/models/task.py`
- Test: `backend/tests/test_task_cancellation.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_task_cancellation.py`:

```python
"""Task cancellation mechanism tests."""

from app.models.task import TaskManager, TaskStatus
from app.services.task_cancelled import TaskCancelledException


def test_cancelled_status_exists():
    assert TaskStatus.CANCELLED == "cancelled"


def test_cancel_task_processing(tmp_path, monkeypatch):
    manager = TaskManager()
    task_id = manager.create_task(task_type="test")
    manager.update_task(task_id, status=TaskStatus.PROCESSING)

    success = manager.cancel_task(task_id)
    assert success is True

    task = manager.get_task(task_id)
    assert task.status == TaskStatus.CANCELLED


def test_cancel_task_not_processing(tmp_path, monkeypatch):
    manager = TaskManager()
    task_id = manager.create_task(task_type="test")
    # Task is PENDING, not PROCESSING
    success = manager.cancel_task(task_id)
    assert success is False

    task = manager.get_task(task_id)
    assert task.status == TaskStatus.PENDING


def test_cancel_task_already_completed(tmp_path, monkeypatch):
    manager = TaskManager()
    task_id = manager.create_task(task_type="test")
    manager.update_task(task_id, status=TaskStatus.COMPLETED)

    success = manager.cancel_task(task_id)
    assert success is False


def test_cancel_task_nonexistent():
    manager = TaskManager()
    success = manager.cancel_task("nonexistent-id")
    assert success is False


def test_task_cancelled_exception():
    exc = TaskCancelledException("task-123", "sequential_reading")
    assert exc.task_id == "task-123"
    assert exc.stage == "sequential_reading"
    assert "task-123" in str(exc)


def test_is_cancelled_helper():
    manager = TaskManager()
    task_id = manager.create_task(task_type="test")
    manager.update_task(task_id, status=TaskStatus.PROCESSING)

    assert manager.is_cancelled(task_id) is False

    manager.cancel_task(task_id)
    assert manager.is_cancelled(task_id) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py -v`
Expected: FAIL with `ImportError` / `AttributeError`

- [ ] **Step 3: Create TaskCancelledException**

Create `backend/app/services/task_cancelled.py`:

```python
"""Exception raised when a running task detects it has been cancelled."""


class TaskCancelledException(Exception):
    """Raised when a worker detects its task has been cancelled."""

    def __init__(self, task_id: str, stage: str = ""):
        self.task_id = task_id
        self.stage = stage
        super().__init__(f"任务已取消: {task_id} (stage={stage})")
```

- [ ] **Step 4: Add CANCELLED status and cancel methods to TaskManager**

In `backend/app/models/task.py`, add to `TaskStatus` enum after `FAILED`:

```python
    CANCELLED = "cancelled"      # 已取消
```

Add two methods to `TaskManager` class after `fail_task`:

```python
    def cancel_task(self, task_id: str) -> bool:
        """Cancel a task. Only PROCESSING tasks can be cancelled.
        
        Returns True if the task was successfully cancelled, False otherwise.
        """
        with self._task_lock:
            task = self._load_task(task_id)
            if not task or task.status != TaskStatus.PROCESSING:
                return False
            task.status = TaskStatus.CANCELLED
            task.message = "用户取消了分析任务"
            task.updated_at = datetime.now()
            self._save_task(task)
            return True

    def is_cancelled(self, task_id: str) -> bool:
        """Check if a task has been cancelled."""
        with self._task_lock:
            task = self._load_task(task_id)
            return task is not None and task.status == TaskStatus.CANCELLED
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py -v`
Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/task_cancelled.py backend/app/models/task.py backend/tests/test_task_cancellation.py
git commit -m "feat: add TaskCancelledException and CANCELLED task status"
```

---

## Task 2: TaskFileLogger

**Files:**
- Create: `backend/app/utils/task_file_logger.py`
- Test: `backend/tests/test_task_file_logger.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_task_file_logger.py`:

```python
"""TaskFileLogger tests."""

import json
import os

from app.utils.task_file_logger import TaskFileLogger


def test_creates_log_file(tmp_path):
    project_dir = str(tmp_path / "project_001")
    os.makedirs(project_dir, exist_ok=True)
    logger = TaskFileLogger(project_dir, "task_001")
    logger.info("sequential_reading", "测试消息")
    logger.close()

    log_path = os.path.join(project_dir, "task_logs", "task_001.log")
    assert os.path.exists(log_path)
    content = open(log_path, "r", encoding="utf-8").read()
    assert "测试消息" in content
    assert "sequential_reading" in content


def test_log_levels(tmp_path):
    project_dir = str(tmp_path / "project_002")
    os.makedirs(project_dir, exist_ok=True)
    logger = TaskFileLogger(project_dir, "task_002")
    logger.info("stage1", "info message")
    logger.warning("stage1", "warn message")
    logger.error("stage1", "error message")
    logger.close()

    log_path = os.path.join(project_dir, "task_logs", "task_002.log")
    content = open(log_path, "r", encoding="utf-8").read()
    assert "[INFO]" in content
    assert "[WARN]" in content
    assert "[ERROR]" in content


def test_log_llm_call(tmp_path):
    project_dir = str(tmp_path / "project_003")
    os.makedirs(project_dir, exist_ok=True)
    logger = TaskFileLogger(project_dir, "task_003")

    prompt = "这是一个很长的提示" * 100  # 800 chars
    response = '{"segment_summary": "摘要内容很长"}' + "x" * 2000  # >1000 chars

    logger.log_llm_call(
        stage="sequential_reading",
        module="sequential_reading",
        model="deepseek-chat",
        prompt=prompt,
        response=response,
        elapsed_ms=12345,
    )
    logger.close()

    log_path = os.path.join(project_dir, "task_logs", "task_003.log")
    content = open(log_path, "r", encoding="utf-8").read()
    assert "deepseek-chat" in content
    assert "12345" in content or "12.3" in content
    # Prompt should be truncated to 500 chars
    assert "prompt_preview" in content
    # Response should be truncated to 1000 chars
    assert "response_preview" in content
    assert "prompt_chars" in content


def test_log_stage_timing(tmp_path):
    project_dir = str(tmp_path / "project_004")
    os.makedirs(project_dir, exist_ok=True)
    logger = TaskFileLogger(project_dir, "task_004")
    logger.stage_start("sequential_reading", detail="共 5 个段落")
    logger.stage_end("sequential_reading", elapsed_s=25.3, detail="完成")
    logger.close()

    log_path = os.path.join(project_dir, "task_logs", "task_004.log")
    content = open(log_path, "r", encoding="utf-8").read()
    assert "sequential_reading" in content
    assert "25.3" in content


def test_close_is_idempotent(tmp_path):
    project_dir = str(tmp_path / "project_005")
    os.makedirs(project_dir, exist_ok=True)
    logger = TaskFileLogger(project_dir, "task_005")
    logger.info("test", "msg")
    logger.close()
    logger.close()  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_file_logger.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `backend/app/utils/task_file_logger.py`:

```python
"""Per-task file logger with LLM call detail logging."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional


class TaskFileLogger:
    """Writes structured logs for a single task to a file in the project directory.

    Log file location: ``<project_dir>/task_logs/<task_id>.log``

    Format::

        [2026-04-03 14:23:01] [INFO] [stage] message

    LLM call details are logged as indented JSON blocks.
    """

    def __init__(self, project_dir: str, task_id: str) -> None:
        self.task_id = task_id
        log_dir = os.path.join(project_dir, "task_logs")
        os.makedirs(log_dir, exist_ok=True)
        self._log_path = os.path.join(log_dir, f"{task_id}.log")
        self._handler = logging.FileHandler(self._log_path, encoding="utf-8")
        self._handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger = logging.getLogger(f"task.{task_id}")
        self._logger.addHandler(self._handler)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._closed = False

    def _format(self, level: str, stage: str, message: str) -> str:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return f"[{ts}] [{level}] [{stage}] {message}"

    def info(self, stage: str, message: str) -> None:
        if not self._closed:
            self._logger.info(self._format("INFO", stage, message))

    def warning(self, stage: str, message: str) -> None:
        if not self._closed:
            self._logger.warning(self._format("WARN", stage, message))

    def error(self, stage: str, message: str) -> None:
        if not self._closed:
            self._logger.error(self._format("ERROR", stage, message))

    def stage_start(self, stage: str, detail: str = "") -> None:
        msg = f"▶ 阶段开始: {stage}"
        if detail:
            msg += f" — {detail}"
        self.info(stage, msg)

    def stage_end(self, stage: str, elapsed_s: float = 0, detail: str = "") -> None:
        msg = f"✓ 阶段结束: {stage}, 耗时 {elapsed_s:.1f}s"
        if detail:
            msg += f" — {detail}"
        self.info(stage, msg)

    def log_llm_call(
        self,
        stage: str,
        module: str,
        model: str,
        prompt: str,
        response: str,
        elapsed_ms: int,
    ) -> None:
        """Log an LLM call with truncated prompt/response previews."""
        detail = {
            "module": module,
            "model": model,
            "elapsed_ms": elapsed_ms,
            "prompt_preview": prompt[:500],
            "response_preview": response[:1000],
            "prompt_chars": len(prompt),
            "response_chars": len(response),
        }
        self.info(stage, f"LLM 调用完成 ({model}, {elapsed_ms}ms)")
        if not self._closed:
            detail_str = json.dumps(detail, ensure_ascii=False, indent=2)
            for line in detail_str.split("\n"):
                self._logger.info(f"  {line}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._logger.removeHandler(self._handler)
        self._handler.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_file_logger.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/utils/task_file_logger.py backend/tests/test_task_file_logger.py
git commit -m "feat: add TaskFileLogger for per-task structured logging"
```

---

## Task 3: Cancel API Endpoint

**Files:**
- Modify: `backend/app/api/project.py`
- Modify: `frontend/src/api/project.js`

- [ ] **Step 1: Add cancel endpoint to backend**

In `backend/app/api/project.py`, add after the `extract_story_seed` function (after line ~157):

```python
@project_bp.route("/task/<task_id>/cancel", methods=["POST"])
def cancel_task(task_id):
    try:
        task_manager = TaskManager()
        success = task_manager.cancel_task(task_id)
        if not success:
            task = task_manager.get_task(task_id)
            status = task.status.value if task else "not_found"
            return jsonify({
                "success": False,
                "error": f"无法取消任务（当前状态: {status}）",
            }), 400
        return jsonify({
            "success": True,
            "data": {"task_id": task_id, "status": "cancelled"},
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
```

Make sure `TaskManager` is imported at the top (it should already be via existing imports, but verify).

- [ ] **Step 2: Add cancelTask to frontend API**

In `frontend/src/api/project.js`, add after `getStepTrace`:

```javascript
export function cancelTask(taskId) {
  return post(`/api/project/task/${taskId}/cancel`);
}
```

- [ ] **Step 3: Test the endpoint manually**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py tests/test_new_seed_pipeline.py -v`
Expected: All tests PASS (no regressions)

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/project.py frontend/src/api/project.js
git commit -m "feat: add POST /api/project/task/<task_id>/cancel endpoint"
```

---

## Task 4: Wire Cancellation Into SequentialReader

**Files:**
- Modify: `backend/app/services/sequential_reader.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_task_cancellation.py`:

```python
from app.services.sequential_reader import SequentialReader
from app.services.task_cancelled import TaskCancelledException
import pytest


class FakeCancelReadingClient:
    def chat_json_value(self, messages, temperature=0.3, max_tokens=8192):
        return {
            "segment_summary": "摘要",
            "character_updates": [],
            "relationship_changes": [],
            "plot_threads": [],
            "world_building": [],
            "consistency_notes": [],
            "narrative_phase": "development",
        }


class FakeCancelRouter:
    def build_client(self, module_key):
        return FakeCancelReadingClient()


def _make_test_segments(count=5):
    return [
        {
            "segment_id": f"seg_{i:03d}",
            "chapters": [{"chapter_id": f"ch_{i:04d}", "order": i, "title": f"第{i}章", "content": f"内容{i}" * 50}],
            "chapter_range": str(i),
            "estimated_tokens": 500,
        }
        for i in range(1, count + 1)
    ]


def test_sequential_reader_respects_cancellation():
    """Reader should stop after detecting cancellation between segments."""
    call_count = 0

    def cancel_check():
        nonlocal call_count
        call_count += 1
        if call_count >= 3:  # Cancel after 2 segments
            raise TaskCancelledException("test-task", "sequential_reading")

    reader = SequentialReader(llm_router=FakeCancelRouter(), arc_interval=10)
    segments = _make_test_segments(5)

    with pytest.raises(TaskCancelledException):
        reader.read(segments, use_llm=True, cancel_check=cancel_check)

    # Should have processed only 2 segments before cancellation
    assert call_count == 3


def test_sequential_reader_no_cancel_check():
    """Reader should work normally when no cancel_check is provided."""
    reader = SequentialReader(llm_router=FakeCancelRouter(), arc_interval=10)
    segments = _make_test_segments(3)
    manager = reader.read(segments, use_llm=True)
    assert len(manager.all_segment_summaries) == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py::test_sequential_reader_respects_cancellation -v`
Expected: FAIL (read() doesn't accept cancel_check parameter)

- [ ] **Step 3: Add cancel_check to SequentialReader.read()**

In `backend/app/services/sequential_reader.py`, update the `read` method signature to add `cancel_check`:

```python
    def read(
        self,
        segments: Sequence[Dict],
        use_llm: bool = True,
        progress_callback: Optional[Callable[[str, Dict], None]] = None,
        cancel_check: Optional[Callable[[], None]] = None,
    ) -> ReadingNotesManager:
```

Add cancellation check at the beginning of the segment loop (inside `for idx, segment in enumerate(segments):`, before the progress_callback call):

```python
            # Check for cancellation before each segment
            if cancel_check is not None:
                cancel_check()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Also verify existing reader tests still pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_sequential_reader.py -v`
Expected: All 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/sequential_reader.py backend/tests/test_task_cancellation.py
git commit -m "feat: add cancel_check support to SequentialReader"
```

---

## Task 5: Wire Cancellation Into CharacterAgentProfileGenerator

**Files:**
- Modify: `backend/app/services/character_agent_profile_generator.py`

- [ ] **Step 1: Write the failing test**

Add to `backend/tests/test_task_cancellation.py`:

```python
from app.services.character_agent_profile_generator import CharacterAgentProfileGenerator
from app.services.reading_notes_manager import ReadingNotesManager


class FakeProfileCancelClient:
    def chat_json_value(self, messages, temperature=0.3, max_tokens=4096):
        return {
            "basic_info": {"name": "test", "aliases": [], "identity": "", "status": "alive"},
            "personality": {"core_traits": [], "values": [], "fears": [], "decision_pattern": ""},
            "speech": {"style": "", "verbal_habits": [], "tone_range": "", "example_quotes": []},
            "relationships": [],
            "capabilities": {"skills": [], "limitations": [], "resources": []},
            "knowledge_boundary": {"knows": [], "does_not_know": [], "believes_wrongly": []},
            "motivation": {"ultimate_goal": "", "current_objective": "", "internal_conflict": ""},
        }


class FakeProfileCancelRouter:
    def build_client(self, module_key):
        return FakeProfileCancelClient()


def _manager_with_many_characters():
    manager = ReadingNotesManager()
    for name in ["角色A", "角色B", "角色C", "角色D", "角色E"]:
        for seg in ["seg_001", "seg_002", "seg_003"]:
            manager.merge_character_updates([{
                "name": name, "aliases": [], "is_new": seg == "seg_001",
                "status": "active", "identity": "测试角色",
                "personality_traits": [], "speech_style": "", "goals": "",
                "key_actions": [], "knowledge_gained": [], "quote_examples": [],
            }], seg)
    return manager


def test_profile_generator_respects_cancellation():
    """Generator should stop producing profiles when cancelled."""
    call_count = 0

    def cancel_check():
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            raise TaskCancelledException("test-task", "agent_profiles")

    gen = CharacterAgentProfileGenerator(
        llm_router=FakeProfileCancelRouter(),
        importance_threshold=2,
        max_workers=1,  # Sequential to make cancel predictable
    )
    manager = _manager_with_many_characters()

    with pytest.raises(TaskCancelledException):
        gen.generate(manager, use_llm=True, cancel_check=cancel_check)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py::test_profile_generator_respects_cancellation -v`
Expected: FAIL (generate() doesn't accept cancel_check parameter)

- [ ] **Step 3: Add cancel_check to CharacterAgentProfileGenerator.generate()**

In `backend/app/services/character_agent_profile_generator.py`, update the `generate` method signature:

```python
    def generate(
        self,
        manager: ReadingNotesManager,
        use_llm: bool = True,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        cancel_check: Optional[Callable[[], None]] = None,
    ) -> Dict[str, Any]:
```

Add cancellation check before submitting each character to the thread pool. Replace the `future_to_name` dict comprehension with a loop that checks cancellation:

```python
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_name = {}
            for name in important_names:
                if cancel_check is not None:
                    cancel_check()
                future_to_name[executor.submit(_generate_one, name)] = name
            for future in as_completed(future_to_name):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py tests/test_character_agent_profile_generator.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/character_agent_profile_generator.py backend/tests/test_task_cancellation.py
git commit -m "feat: add cancel_check support to CharacterAgentProfileGenerator"
```

---

## Task 6: Wire Cancellation + Logging Into SeedExtractRunner

**Files:**
- Modify: `backend/app/services/seed_extract_runner.py`
- Modify: `backend/app/services/seed_extract_task_service.py`

This is the integration task — connects cancellation and logging to the pipeline.

- [ ] **Step 1: Update SeedExtractRunner to use TaskFileLogger and cancel checks**

In `backend/app/services/seed_extract_runner.py`:

Add imports at top:

```python
import os
import time

from .task_cancelled import TaskCancelledException
from ..utils.task_file_logger import TaskFileLogger
```

Update `__init__` to create logger and store task_id:

```python
    def __init__(self, service: Any, task_id: str, use_llm: bool, project_id: str = ""):
        self.service = service
        self.task_id = task_id
        self.use_llm = use_llm
        self.progress = SeedTaskProgressTracker(
            service.task_manager, task_id, use_llm, project_id=project_id,
        )
        # Per-task file logger
        if project_id:
            project_dir = ProjectManager._get_project_dir(project_id)
            self.task_logger = TaskFileLogger(project_dir, task_id)
        else:
            self.task_logger = None
```

Add `_check_cancelled` method:

```python
    def _check_cancelled(self) -> None:
        """Check if the task has been cancelled. Raises TaskCancelledException."""
        if self.service.task_manager.is_cancelled(self.task_id):
            raise TaskCancelledException(self.task_id, "runner")
```

Update `run()` to wrap in try/except for cancellation and add logging:

```python
    def run(
        self,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
    ) -> None:
        pipeline_start = time.time()
        if self.task_logger:
            self.task_logger.info("pipeline", f"管线启动: project={project_name}, use_llm={self.use_llm}")

        try:
            self._validate_llm_modules()

            # Stage 1
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("extract_text", "提取文本与智能分段")
            documents, chapter_segments = self._extract_and_segment(project_id)
            if self.task_logger:
                self.task_logger.stage_end("extract_text", time.time() - t0,
                    f"{len(documents)} 份文稿, {chapter_segments.get('smart_segments', {}).get('segment_count', 0)} 个阅读段")

            self._check_cancelled()

            # Stage 2
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("sequential_reading", f"共 {chapter_segments.get('smart_segments', {}).get('segment_count', 0)} 个段落")
            manager = self._sequential_reading(project_id, chapter_segments)
            if self.task_logger:
                chars = len(manager.notes["core_facts"]["characters"])
                self.task_logger.stage_end("sequential_reading", time.time() - t0, f"记录 {chars} 名角色")

            self._check_cancelled()

            # Stage 3
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("global_integration", "聚合分析与本体生成")
            seed_analysis, ontology = self._global_integration_and_ontology(
                project_id, project_name, analysis_goal, additional_context,
                documents, manager,
            )
            if self.task_logger:
                self.task_logger.stage_end("global_integration", time.time() - t0, self._seed_counts_text(seed_analysis))

            self._check_cancelled()

            # Stage 4
            t0 = time.time()
            if self.task_logger:
                self.task_logger.stage_start("agent_profiles", "角色档案生成")
            agent_profiles = self._generate_agent_profiles(project_id, manager)
            if self.task_logger:
                self.task_logger.stage_end("agent_profiles", time.time() - t0, f"{agent_profiles['profile_count']} 个档案")

            # Finalize
            self.service._finalize_project(project_id, analysis_goal, ontology, seed_analysis)
            self.progress.complete(
                "上传完成，项目与种子分析已生成。",
                self._result_payload(project_id, chapter_segments, manager, seed_analysis, agent_profiles),
            )
            if self.task_logger:
                total_s = time.time() - pipeline_start
                self.task_logger.info("pipeline", f"管线完成，总耗时 {total_s:.1f}s")

        except TaskCancelledException as exc:
            if self.task_logger:
                self.task_logger.warning("pipeline", f"任务被用户取消 (stage={exc.stage})")
            self.service._fail_project(project_id, "用户取消了分析任务")
            self.progress.fail("用户取消了分析任务")

        finally:
            if self.task_logger:
                self.task_logger.close()
```

- [ ] **Step 2: Pass cancel_check to SequentialReader and CharacterAgentProfileGenerator**

In `_sequential_reading`, update the `self.service.sequential_reader.read()` call to pass `cancel_check`:

```python
        manager = self.service.sequential_reader.read(
            segments=segments,
            use_llm=self.use_llm,
            progress_callback=reading_progress_callback,
            cancel_check=self._check_cancelled,
        )
```

In `_generate_agent_profiles`, update the `self.service.character_agent_profile_generator.generate()` call:

```python
        agent_profiles = self.service.character_agent_profile_generator.generate(
            manager=manager,
            use_llm=self.use_llm,
            progress_callback=profile_progress_callback,
            cancel_check=self._check_cancelled,
        )
```

- [ ] **Step 3: Update SeedExtractTaskService._run_worker to handle TaskCancelledException**

In `backend/app/services/seed_extract_task_service.py`, update `_run_worker`:

```python
    def _run_worker(
        self,
        task_id: str,
        project_id: str,
        project_name: str,
        analysis_goal: str,
        additional_context: str,
        use_llm: bool,
        segment_token_limit: int = 50000,
    ) -> None:
        self.smart_segmenter = SmartNovelSegmenter(target_token_limit=segment_token_limit)
        runner = SeedExtractRunner(self, task_id, use_llm, project_id=project_id)
        try:
            runner.run(project_id, project_name, analysis_goal, additional_context)
        except TaskCancelledException:
            # Already handled inside runner.run() — project marked failed, progress updated
            pass
        except Exception as exc:
            message = format_upstream_service_error(exc)
            self._fail_project(project_id, message)
            runner.progress.fail(message)
```

Add the import at the top of the file:

```python
from .task_cancelled import TaskCancelledException
```

- [ ] **Step 4: Run integration tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_new_seed_pipeline.py tests/test_task_cancellation.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/seed_extract_runner.py backend/app/services/seed_extract_task_service.py
git commit -m "feat: wire cancellation checks and per-task logging into pipeline runner"
```

---

## Task 7: Frontend Cancel Button

**Files:**
- Modify: `frontend/src/composables/useSeedUpload.js`
- Modify: `frontend/src/views/overview/SeedUploadFormFields.vue`

- [ ] **Step 1: Add cancelUpload to useSeedUpload.js**

In `frontend/src/composables/useSeedUpload.js`:

Add import at top:

```javascript
import { cancelTask, getTask, uploadStorySeed } from "../api/project";
```

(Replace the existing import of `getTask, uploadStorySeed` from `../api/project`.)

Add `cancelUpload` function before `clearNotice`:

```javascript
async function cancelUpload() {
  if (!state.taskId || state.taskStatus !== "processing") {
    return;
  }
  try {
    await cancelTask(state.taskId);
    state.uploadBusy = false;
    state.uploadPhase = "error";
    state.taskStatus = "cancelled";
    state.error = "分析任务已取消";
    state.statusText = "分析任务已取消";
    resetStructuredView(state);
    activeUploadPromise = null;
    activeUploadRequest = null;
  } catch (error) {
    state.error = error.message || "取消失败";
  }
}
```

Export it alongside other methods:

```javascript
export function useSeedUpload() {
  return {
    state,
    fileKey,
    appendFiles,
    removeFile,
    formatSize,
    submitUpload,
    cancelUpload,
    clearNotice,
  };
}
```

- [ ] **Step 2: Add cancel button to SeedUploadFormFields.vue**

In `frontend/src/views/overview/SeedUploadFormFields.vue`, replace the upload actions section:

```html
    <div class="upload-actions">
      <button class="btn primary large" :disabled="!canSubmit || upload.state.uploadBusy" @click="submitUpload">
        {{ upload.state.uploadBusy ? "分析进行中..." : "开始分析" }}
      </button>
      <button
        v-if="upload.state.uploadBusy && upload.state.uploadPhase === 'processing'"
        class="btn cancel-btn"
        @click="confirmCancel"
      >
        取消分析
      </button>
    </div>
```

Add the `showCancelConfirm` ref, `confirmCancel` and `doCancel` functions:

```javascript
const showCancelConfirm = ref(false);

function confirmCancel() {
  if (confirm("确定要取消当前分析任务吗？已完成的分析数据将保留。")) {
    upload.cancelUpload();
  }
}
```

Add cancel button styles:

```css
.upload-actions {
  display: flex;
  justify-content: center;
  gap: var(--space-md);
  margin-top: var(--space-md);
}

.cancel-btn {
  padding: 14px 32px;
  font-size: 16px;
  background: transparent;
  border: 1px solid var(--accent-seal, #9b4326);
  color: var(--accent-seal, #9b4326);
  border-radius: var(--radius-md, 8px);
  cursor: pointer;
  transition: all 0.2s ease;
}

.cancel-btn:hover {
  background: rgba(155, 67, 38, 0.08);
}
```

- [ ] **Step 3: Update uploadStorySeed to pass segmentTokenLimit**

Verify that `frontend/src/api/project.js`'s `uploadStorySeed` function already passes `segmentTokenLimit` in the FormData (it was added in the previous plan's Task 9). If not, add:

```javascript
  if (segmentTokenLimit) {
    formData.append("segment_token_limit", String(segmentTokenLimit));
  }
```

And update the destructured params:

```javascript
export function uploadStorySeed({
  projectName,
  analysisGoal,
  additionalContext,
  segmentTokenLimit,
  files = [],
  onProgress,
  onRequest,
}) {
```

- [ ] **Step 4: Verify frontend builds**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add frontend/src/composables/useSeedUpload.js frontend/src/views/overview/SeedUploadFormFields.vue frontend/src/api/project.js
git commit -m "feat: add cancel button with confirmation dialog for running pipeline"
```

---

## Task 8: Full Verification

**Files:** No new files.

- [ ] **Step 1: Run all cancellation + logger tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_task_cancellation.py tests/test_task_file_logger.py -v`
Expected: All tests PASS

- [ ] **Step 2: Run new pipeline e2e tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_new_seed_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run all new service tests**

Run: `cd /root/novelwork/backend && PYTHONPATH=$(pwd) pytest tests/test_smart_novel_segmenter.py tests/test_reading_notes_manager.py tests/test_sequential_reader.py tests/test_character_agent_profile_generator.py tests/test_seed_analysis_from_reading_notes.py -v`
Expected: All tests PASS

- [ ] **Step 4: Verify frontend build**

Run: `cd /root/novelwork/frontend && npm run build`
Expected: Build succeeds
