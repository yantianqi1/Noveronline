"""Tests for TaskCancelledException and TaskStatus.CANCELLED."""

import pytest

from app.models.task import TaskManager, TaskStatus
from app.services.task_cancelled import TaskCancelledException
from app.services.sequential_reader import SequentialReader
from app.services.character_agent_profile_generator import CharacterAgentProfileGenerator
from app.services.reading_notes_manager import ReadingNotesManager


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


# ---------------------------------------------------------------------------
# SequentialReader cancel_check tests (Task 4)
# ---------------------------------------------------------------------------

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
    call_count = 0

    def cancel_check():
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            raise TaskCancelledException("test-task", "sequential_reading")

    reader = SequentialReader(llm_router=FakeCancelRouter(), arc_interval=10)
    segments = _make_test_segments(5)

    with pytest.raises(TaskCancelledException):
        reader.read(segments, use_llm=True, cancel_check=cancel_check)

    assert call_count == 3


def test_sequential_reader_no_cancel_check():
    reader = SequentialReader(llm_router=FakeCancelRouter(), arc_interval=10)
    segments = _make_test_segments(3)
    manager = reader.read(segments, use_llm=True)
    assert len(manager.all_segment_summaries) == 3


# ---------------------------------------------------------------------------
# CharacterAgentProfileGenerator cancel_check tests (Task 5)
# ---------------------------------------------------------------------------

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
    call_count = 0

    def cancel_check():
        nonlocal call_count
        call_count += 1
        if call_count >= 3:
            raise TaskCancelledException("test-task", "agent_profiles")

    gen = CharacterAgentProfileGenerator(
        llm_router=FakeProfileCancelRouter(),
        importance_threshold=2,
        max_workers=1,
    )
    manager = _manager_with_many_characters()

    with pytest.raises(TaskCancelledException):
        gen.generate(manager, use_llm=True, cancel_check=cancel_check)
