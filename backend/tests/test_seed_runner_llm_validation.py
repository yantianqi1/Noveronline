import pytest

from app.models.task import TaskManager
from app.services.seed_extract_runner import SeedExtractRunner


class DummyService:
    def __init__(self):
        self.task_manager = TaskManager()


def test_seed_runner_preserves_use_llm_flag():
    service = DummyService()
    task_id = service.task_manager.sync_bridge(service.task_manager.create_task(task_type="seed_extract", metadata={}))

    runner = SeedExtractRunner(service, task_id, use_llm=False)

    assert runner.use_llm is False
    assert runner.progress.use_llm is False


def test_seed_runner_skips_llm_validation_when_use_llm_disabled(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.sync_bridge(service.task_manager.create_task(task_type="seed_extract", metadata={}))

    class FakeRouter:
        def build_client(self, module_key):
            raise AssertionError(f"should not validate {module_key}")

    monkeypatch.setattr("app.services.seed_extract_runner.LlmRouter", lambda: FakeRouter())

    runner = SeedExtractRunner(service, task_id, use_llm=False)

    runner._validate_llm_modules()


def test_seed_runner_llm_validation_reports_missing_bindings(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.sync_bridge(service.task_manager.create_task(task_type="seed_extract", metadata={}))

    class FakeRouter:
        def build_client(self, module_key):
            if module_key == "sequential_reading":
                raise ValueError("剧情锚点摘要 未配置 LLM 渠道和模型；请先在全局设施面板完成绑定")
            return object()

    monkeypatch.setattr("app.services.seed_extract_runner.LlmRouter", lambda: FakeRouter())

    runner = SeedExtractRunner(service, task_id, use_llm=True)

    with pytest.raises(ValueError, match="sequential_reading"):
        runner._validate_llm_modules()


def test_seed_runner_llm_validation_only_requires_active_pipeline_modules(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.sync_bridge(service.task_manager.create_task(task_type="seed_extract", metadata={}))

    class FakeRouter:
        def build_client(self, module_key):
            if module_key in {"sequential_reading", "story_ontology", "character_agent_profile"}:
                return object()
            raise AssertionError(f"deprecated module should not be validated: {module_key}")

    monkeypatch.setattr("app.services.seed_extract_runner.LlmRouter", lambda: FakeRouter())

    runner = SeedExtractRunner(service, task_id, use_llm=True)

    runner._validate_llm_modules()


def test_seed_runner_llm_validation_does_not_swallow_runtime_errors(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.sync_bridge(service.task_manager.create_task(task_type="seed_extract", metadata={}))

    class FakeRouter:
        def build_client(self, module_key):
            raise RuntimeError(f"boom:{module_key}")

    monkeypatch.setattr("app.services.seed_extract_runner.LlmRouter", lambda: FakeRouter())

    runner = SeedExtractRunner(service, task_id, use_llm=True)

    with pytest.raises(RuntimeError, match="boom:sequential_reading"):
        runner._validate_llm_modules()


def test_seed_runner_records_unified_db_ready_note(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.sync_bridge(service.task_manager.create_task(task_type="seed_extract", metadata={}))
    runner = SeedExtractRunner(service, task_id, use_llm=False)

    captured = {}

    def fake_note(stage, title, detail, meta=None):
        captured.update({
            "stage": stage,
            "title": title,
            "detail": detail,
            "meta": meta,
        })

    monkeypatch.setattr(runner.progress, "note", fake_note)

    runner._record_unified_db_ready()

    assert captured == {
        "stage": "agent_profiles",
        "title": "统一数据库已就绪",
        "detail": "后续写作与检索将直接使用主库，不再回填 legacy novel.sqlite3",
        "meta": {"kind": "migration", "target": "unified_db"},
    }
