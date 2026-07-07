from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_phase3_local_infra_compose_declares_required_dependencies() -> None:
    compose_path = ROOT / "infra" / "docker-compose.yml"
    compose = compose_path.read_text(encoding="utf-8")

    for service in ("postgres:", "redis:", "temporal:", "minio:"):
        assert service in compose

    for image in (
        "postgres:16",
        "redis:7",
        "temporalio/auto-setup",
        "minio/minio",
    ):
        assert image in compose

    for healthcheck in (
        "pg_isready",
        "redis-cli ping",
        "temporal operator cluster health",
        "minio/health/ready",
    ):
        assert healthcheck in compose

    for volume in (
        "postgres_data:",
        "redis_data:",
        "minio_data:",
    ):
        assert volume in compose


def test_phase3_infra_documents_pi_runtime_node_floor() -> None:
    package_json = json.loads(
        (ROOT / "apps" / "pi-agent-runtime" / "package.json").read_text(
            encoding="utf-8",
        ),
    )
    assert package_json["engines"]["node"] == ">=22.19.0"

    env_example = (ROOT / "infra" / ".env.example").read_text(encoding="utf-8")
    assert "PI_AGENT_RUNTIME_NODE_VERSION=22.19.0" in env_example


def test_phase3_compose_declares_python_agent_runtime_worker() -> None:
    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = ROOT / "apps" / "agent-runtime" / "Dockerfile"

    assert "agent-runtime:" in compose
    assert "agent-runtime-seed:" in compose
    assert "context: ../apps/agent-runtime" in compose
    assert "TEMPORAL_ADDRESS: temporal:7233" in compose
    assert "AGENT_RUNTIME_TASK_QUEUE: seed-heavy" in compose
    assert "python -m mirofish_agents.temporal.worker" in compose
    assert dockerfile.exists()


def test_phase5_compose_initializes_source_file_object_bucket() -> None:
    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / "infra" / ".env.example").read_text(encoding="utf-8")

    assert "minio-init:" in compose
    assert "minio/mc" in compose
    assert "mb --ignore-existing" in compose
    assert "MIROFISH_OBJECT_STORAGE_BUCKET=mirofish-uploads" in env_example
    assert "MIROFISH_OBJECT_STORAGE_ENDPOINT=127.0.0.1:9000" in env_example


def test_phase5_seed_worker_has_object_storage_and_artifact_db_binding() -> None:
    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "agent-runtime-seed:" in compose
    assert "DATABASE_URL: postgresql://" in compose
    assert "MIROFISH_OBJECT_STORAGE_ENDPOINT: minio:9000" in compose
    assert "MIROFISH_OBJECT_STORAGE_BUCKET: ${MIROFISH_OBJECT_STORAGE_BUCKET:-mirofish-uploads}" in compose
    assert "MIROFISH_OBJECT_STORAGE_ACCESS_KEY: ${MINIO_ROOT_USER:-mirofish}" in compose
    assert "MIROFISH_OBJECT_STORAGE_SECRET_KEY: ${MINIO_ROOT_PASSWORD:-mirofish_dev_password}" in compose
    assert "MIROFISH_OBJECT_STORAGE_USE_SSL: \"false\"" in compose


def test_phase5_graph_worker_has_dedicated_task_queue_and_db_binding() -> None:
    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")

    assert "agent-runtime-graph:" in compose
    assert "AGENT_RUNTIME_TASK_QUEUE: graph-heavy" in compose
    assert "DATABASE_URL: postgresql://" in compose
    assert "python -m mirofish_agents.temporal.worker" in compose


def test_phase3_compose_declares_pi_writer_runtime_worker() -> None:
    compose = (ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = ROOT / "apps" / "pi-agent-runtime" / "Dockerfile"

    assert "pi-agent-runtime:" in compose
    assert "context: ../apps/pi-agent-runtime" in compose
    assert "TEMPORAL_ADDRESS: temporal:7233" in compose
    assert "WRITER_TASK_QUEUE: writer-streaming" in compose
    assert "DATABASE_URL:" in compose
    assert "LLM_CREDENTIAL_ENCRYPTION_KEY:" in compose
    assert "npm run worker" in compose
    assert dockerfile.exists()
