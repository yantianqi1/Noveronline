from bootstrap import build_worker_bootstrap
from worker import describe_worker, load_worker_bootstrap, load_worker_settings


def test_worker_settings_defaults(monkeypatch):
    monkeypatch.delenv("MIROFISH_TEMPORAL_TARGET", raising=False)
    monkeypatch.delenv("MIROFISH_TEMPORAL_NAMESPACE", raising=False)
    monkeypatch.delenv("MIROFISH_TASK_QUEUE", raising=False)
    monkeypatch.delenv("MIROFISH_WORKER_NAME", raising=False)

    settings = load_worker_settings()

    assert settings.temporal_target == "127.0.0.1:7233"
    assert settings.temporal_namespace == "default"
    assert settings.task_queue == "mirofish-main"
    assert settings.worker_name == "mirofish-novel-worker"


def test_worker_bootstrap_and_description_share_the_same_contract(monkeypatch):
    monkeypatch.delenv("MIROFISH_TEMPORAL_TARGET", raising=False)
    monkeypatch.delenv("MIROFISH_TEMPORAL_NAMESPACE", raising=False)
    monkeypatch.delenv("MIROFISH_TASK_QUEUE", raising=False)
    monkeypatch.delenv("MIROFISH_WORKER_NAME", raising=False)

    bootstrap = build_worker_bootstrap()
    loaded_bootstrap = load_worker_bootstrap()
    description = describe_worker()

    assert bootstrap.as_dict() == loaded_bootstrap.as_dict()
    assert description == bootstrap.as_dict()
    assert description["settings"]["temporal_target"] == "127.0.0.1:7233"
    assert description["task_queue"]["name"] == "mirofish-main"
