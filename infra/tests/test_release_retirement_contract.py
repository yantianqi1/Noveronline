from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "docs" / "refactor-saas" / "25-release-retirement-and-compatibility.md"
COMPOSE_FILES = (
    ROOT / "infra" / "docker-compose.yml",
    ROOT / "infra" / "compose.staging.yml",
    ROOT / "infra" / "compose.production.yml",
)


def test_retirement_decision_records_exact_release_replacements_and_blockers() -> None:
    decision = DECISION.read_text(encoding="utf-8")
    for required in (
        "Self-service signup",
        "OAuth login",
        "MFA enrollment/challenge",
        "GET /api/v2/chapter-context/options",
        "POST /api/v2/chapter-context/builds",
        "POST /api/v2/drafts",
        "POST /api/writer-agent/world-update",
        "explicit user adoption",
        "410 Gone",
        "current_world",
        "Dynamic registry",
        "realtime activity push",
        "external HTTPS provider",
        "non-empty selected legacy source",
    ):
        assert required in decision
    assert "not required for release completion" in decision
    assert "Partial or empty imports remain partial" in decision


def test_release_compose_never_mounts_or_starts_legacy_application_runtime() -> None:
    for path in COMPOSE_FILES:
        encoded = path.read_text(encoding="utf-8")
        for forbidden in (
            "../backend",
            "../frontend",
            "backend/data",
            "backend/uploads",
            "uvicorn",
            "run.py",
            "APP_PORT=3888",
        ):
            assert forbidden not in encoded, f"{path.name} restores legacy runtime through {forbidden}"


def test_release_compose_has_no_legacy_single_provider_environment_fallback() -> None:
    for path in COMPOSE_FILES:
        encoded = path.read_text(encoding="utf-8")
        for forbidden in (
            "LLM_API_KEY",
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "OPENAI_MODEL",
            "LLM_MODEL=",
            "LLM_BASE_URL",
        ):
            assert forbidden not in encoded, f"{path.name} restores provider env fallback {forbidden}"
        assert "LLM_CREDENTIAL_ENCRYPTION_KEY" in encoded


def test_only_explicit_legacy_import_mount_can_read_repo_owned_legacy_input() -> None:
    base = COMPOSE_FILES[0].read_text(encoding="utf-8")
    assert base.count("./legacy-import-source:/legacy-import-source:ro") == 1
    assert "LEGACY_IMPORT_SOURCE_ROOT: /legacy-import-source" in base
    assert "${LEGACY_IMPORT_SOURCE_ROOT" not in "\n".join(
        path.read_text(encoding="utf-8") for path in COMPOSE_FILES
    )
