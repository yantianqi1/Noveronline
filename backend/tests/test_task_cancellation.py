"""Tests for TaskCancelledException and TaskStatus.CANCELLED."""

import pytest

from app.models.task import TaskManager, TaskStatus
from app.services.task_cancelled import TaskCancelledException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_manager() -> TaskManager:
    """Return a TaskManager wired to a fresh temp-file SQLite DB."""
    import tempfile
    from app.models.task_storage import TaskStorage

    # Reset the singleton so each test gets an isolated instance
    TaskManager._instance = None
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite3", delete=False)
    tmp.close()
    storage = TaskStorage(tmp.name)
    mgr = TaskManager()
    mgr._storage = storage
    return mgr


# ---------------------------------------------------------------------------
# 1. TaskStatus.CANCELLED exists and has the expected value
# ---------------------------------------------------------------------------

def test_cancelled_status_exists():
    assert TaskStatus.CANCELLED == "cancelled"


# ---------------------------------------------------------------------------
# 2. cancel_task on a PROCESSING task returns True and flips status
# ---------------------------------------------------------------------------

def test_cancel_task_processing():
    mgr = make_manager()
    task_id = mgr.create_task("test_type")
    mgr.update_task(task_id, status=TaskStatus.PROCESSING)

    result = mgr.cancel_task(task_id)

    assert result is True
    task = mgr.get_task(task_id)
    assert task.status == TaskStatus.CANCELLED


# ---------------------------------------------------------------------------
# 3. cancel_task on a PENDING task returns False and leaves status unchanged
# ---------------------------------------------------------------------------

def test_cancel_task_not_processing():
    mgr = make_manager()
    task_id = mgr.create_task("test_type")
    # Status is PENDING by default

    result = mgr.cancel_task(task_id)

    assert result is False
    task = mgr.get_task(task_id)
    assert task.status == TaskStatus.PENDING


# ---------------------------------------------------------------------------
# 4. cancel_task on a COMPLETED task returns False
# ---------------------------------------------------------------------------

def test_cancel_task_already_completed():
    mgr = make_manager()
    task_id = mgr.create_task("test_type")
    mgr.complete_task(task_id, result={"ok": True})

    result = mgr.cancel_task(task_id)

    assert result is False
    task = mgr.get_task(task_id)
    assert task.status == TaskStatus.COMPLETED


# ---------------------------------------------------------------------------
# 5. cancel_task on a nonexistent ID returns False
# ---------------------------------------------------------------------------

def test_cancel_task_nonexistent():
    mgr = make_manager()

    result = mgr.cancel_task("00000000-0000-0000-0000-000000000000")

    assert result is False


# ---------------------------------------------------------------------------
# 6. TaskCancelledException carries task_id and stage
# ---------------------------------------------------------------------------

def test_task_cancelled_exception():
    exc = TaskCancelledException(task_id="abc-123", stage="embedding")

    assert exc.task_id == "abc-123"
    assert exc.stage == "embedding"
    assert isinstance(exc, Exception)
    assert "abc-123" in str(exc)
    assert "embedding" in str(exc)


# ---------------------------------------------------------------------------
# 7. is_cancelled returns False while processing, True after cancel
# ---------------------------------------------------------------------------

def test_is_cancelled_helper():
    mgr = make_manager()
    task_id = mgr.create_task("test_type")
    mgr.update_task(task_id, status=TaskStatus.PROCESSING)

    assert mgr.is_cancelled(task_id) is False

    mgr.cancel_task(task_id)

    assert mgr.is_cancelled(task_id) is True
