import pytest

from app.models.task import TaskManager
from app.services.seed_extract_runner import SeedExtractRunner


class DummyService:
    def __init__(self):
        self.task_manager = TaskManager()


def test_seed_runner_preserves_use_llm_flag():
    service = DummyService()
    task_id = service.task_manager.create_task(task_type="seed_extract", metadata={})

    runner = SeedExtractRunner(service, task_id, use_llm=False)

    assert runner.use_llm is False
    assert runner.progress.use_llm is False


def test_seed_runner_skips_llm_validation_when_use_llm_disabled(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.create_task(task_type="seed_extract", metadata={})

    class FakeRouter:
        def build_client(self, module_key):
            raise AssertionError(f"should not validate {module_key}")

    monkeypatch.setattr("app.services.seed_extract_runner.LlmRouter", lambda: FakeRouter())

    runner = SeedExtractRunner(service, task_id, use_llm=False)

    runner._validate_llm_modules()


def test_seed_runner_llm_validation_reports_missing_bindings(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.create_task(task_type="seed_extract", metadata={})

    class FakeRouter:
        def build_client(self, module_key):
            if module_key == "novel_chapter_summarizer":
                raise ValueError("剧情锚点摘要 未配置 LLM 渠道和模型；请先在全局设施面板完成绑定")
            return object()

    monkeypatch.setattr("app.services.seed_extract_runner.LlmRouter", lambda: FakeRouter())

    runner = SeedExtractRunner(service, task_id, use_llm=True)

    with pytest.raises(ValueError, match="novel_chapter_summarizer"):
        runner._validate_llm_modules()


def test_seed_runner_llm_validation_does_not_swallow_runtime_errors(monkeypatch):
    service = DummyService()
    task_id = service.task_manager.create_task(task_type="seed_extract", metadata={})

    class FakeRouter:
        def build_client(self, module_key):
            raise RuntimeError(f"boom:{module_key}")

    monkeypatch.setattr("app.services.seed_extract_runner.LlmRouter", lambda: FakeRouter())

    runner = SeedExtractRunner(service, task_id, use_llm=True)

    with pytest.raises(RuntimeError, match="boom:local_block_facts"):
        runner._validate_llm_modules()
