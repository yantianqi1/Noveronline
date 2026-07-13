from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


INFRA = Path(__file__).resolve().parents[1]


def _valid_config() -> dict[str, str]:
    return {
        **os.environ,
        "MIROFISH_DEPLOYMENT_ENV": "production",
        "COMPOSE_PROJECT_NAME": "mirofish-production",
        "POSTGRES_DB": "mirofish",
        "POSTGRES_USER": "admin",
        "POSTGRES_PASSWORD": "admin-database-secret",
        "APP_DATABASE_USER": "runtime",
        "APP_DATABASE_PASSWORD": "runtime-database-secret",
        "DATABASE_URL": "postgresql://runtime:secret@db/mirofish",
        "MIROFISH_AUTH_SESSION_SECRET": "s" * 32,
        "MIROFISH_RECOVERY_CLIENT_PROOF_SECRET": "p" * 32,
        "MIROFISH_TRUSTED_CLIENT_IP_HEADER": "X-Real-IP",
        "AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY": "dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHR0dHQ=",
        "LLM_CREDENTIAL_ENCRYPTION_KEY": "valid-key-material",
        "MINIO_ROOT_USER": "storage",
        "MINIO_ROOT_PASSWORD": "storage-secret-value",
        "MIROFISH_OBJECT_STORAGE_ENDPOINT": "minio:9000",
        "MIROFISH_OBJECT_STORAGE_BUCKET": "mirofish-production-uploads",
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY": "storage-access-key",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY": "storage-object-secret",
        "MIROFISH_OBJECT_STORAGE_USE_SSL": "false",
        "MIROFISH_OBJECT_STORAGE_REGION": "us-east-1",
        "TEMPORAL_NAMESPACE": "mirofish-production",
        "MIROFISH_AUTH_RATE_LIMIT_REDIS_URL": "redis://redis:6379/0",
        "MIROFISH_RATE_LIMIT_KEY_SECRET": "r" * 32,
        "MIROFISH_RATE_LIMIT_POLICIES_JSON": '{"auth_login":{"limit":10,"window_seconds":60},"auth_signup":{"limit":5,"window_seconds":300},"auth_session_mutation":{"limit":20,"window_seconds":60},"collaboration_invite_create":{"limit":10,"window_seconds":60},"collaboration_invite_accept":{"limit":20,"window_seconds":60},"llm_admin_mutation":{"limit":20,"window_seconds":60},"llm_provider_health":{"limit":30,"window_seconds":60}}',
        "SMTP_HOST": "smtp.example.test",
        "SMTP_PORT": "465",
        "SMTP_USERNAME": "smtp-user",
        "SMTP_PASSWORD": "smtp-secret-value",
        "SMTP_FROM": "no-reply@example.test",
        "SMTP_TLS_MODE": "implicit_tls",
        "AUTH_RECOVERY_RESET_BASE_URL": "https://app.example.test/recovery/reset",
        "COLLABORATION_ACCEPT_BASE_URL": "https://app.example.test/invitations/accept",
        "API_PORT": "3888",
        "WEB_PORT": "3999",
    }


def _validate(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(INFRA / "scripts" / "validate-deployment-config.sh")],
        env=env,
        text=True,
        capture_output=True,
    )


def test_production_overrides_do_not_contain_development_secrets() -> None:
    encoded = (INFRA / "compose.production.yml").read_text(encoding="utf-8")
    assert "mirofish_dev_password" not in encoded
    assert "mirofish_local_compose_session_secret" not in encoded
    assert "MIROFISH_WEB_DEV_BYPASS_LOGIN: \"0\"" in encoded
    assert "legacy-import-worker:" in encoded


def test_writer_planning_worker_has_staging_and_production_runtime_contracts() -> None:
    for name in ("compose.staging.yml", "compose.production.yml"):
        encoded = (INFRA / name).read_text(encoding="utf-8")
        next_service = "pi-agent-runtime" if name == "compose.production.yml" else "legacy-import-worker"
        section = encoded.split("  agent-runtime-writer-planning:", 1)[1].split(f"\n  {next_service}:", 1)[0]
        assert "${DATABASE_URL:?DATABASE_URL is required}" in section
        assert "${LLM_CREDENTIAL_ENCRYPTION_KEY:?LLM_CREDENTIAL_ENCRYPTION_KEY is required}" in section
        if name == "compose.production.yml":
            assert "security_opt: *service-security" in section


def test_base_compose_legacy_worker_uses_fixed_read_only_local_source_root() -> None:
    encoded = (INFRA / "docker-compose.yml").read_text(encoding="utf-8")
    section = encoded.split("  legacy-import-worker:", 1)[1].split("\n  pi-agent-runtime:", 1)[0]
    assert "LEGACY_IMPORT_SOURCE_ROOT: /legacy-import-source" in section
    assert "./legacy-import-source:/legacy-import-source:ro" in section
    assert "${LEGACY_IMPORT_SOURCE_ROOT" not in section


def test_staging_and_production_require_runtime_recovery_and_delivery_configuration() -> None:
    required = (
        "MIROFISH_RECOVERY_CLIENT_PROOF_SECRET",
        "MIROFISH_TRUSTED_CLIENT_IP_HEADER",
        "AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY",
        "MIROFISH_DEPLOYMENT_ENV",
        "MIROFISH_AUTH_RATE_LIMIT_REDIS_URL",
        "MIROFISH_RATE_LIMIT_KEY_SECRET",
        "MIROFISH_RATE_LIMIT_POLICIES_JSON",
        "TEMPORAL_NAMESPACE",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_TLS_MODE",
        "AUTH_RECOVERY_RESET_BASE_URL",
        "COLLABORATION_ACCEPT_BASE_URL",
        "MIROFISH_OBJECT_STORAGE_ENDPOINT",
        "MIROFISH_OBJECT_STORAGE_BUCKET",
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
        "MIROFISH_OBJECT_STORAGE_USE_SSL",
        "MIROFISH_OBJECT_STORAGE_REGION",
    )
    for name in ("compose.staging.yml", "compose.production.yml"):
        encoded = (INFRA / name).read_text(encoding="utf-8")
        for variable in required:
            assert f"${{{variable}:?{variable} is required}}" in encoded
        api_section = encoded.split("  api:", 1)[1].split("\n  web:", 1)[0]
        for readiness_variable in (
            "TEMPORAL_NAMESPACE",
            "MIROFISH_OBJECT_STORAGE_ENDPOINT",
            "MIROFISH_OBJECT_STORAGE_BUCKET",
            "MIROFISH_OBJECT_STORAGE_ACCESS_KEY",
            "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
            "MIROFISH_OBJECT_STORAGE_USE_SSL",
        ):
            assert f"${{{readiness_variable}:?{readiness_variable} is required}}" in api_section
        assert "MIROFISH_SMTP_" not in encoded
        assert "MIROFISH_PUBLIC_PASSWORD_RESET_URL" not in encoded
        assert "MIROFISH_PUBLIC_INVITATION_ACCEPT_URL" not in encoded
        assert "LEGACY_IMPORT_SOURCE_ROOT: /legacy-import-source" in encoded
        assert "${LEGACY_IMPORT_SOURCE_ROOT" not in encoded
        assert "mc version enable" in encoded


def test_restore_requires_explicit_disposable_confirmation(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(INFRA / "scripts" / "restore-postgres-minio.sh")],
        env={
            **os.environ,
            "RESTORE_BACKUP_DIR": str(tmp_path),
            "RESTORE_CONFIRM": "no",
            "RESTORE_DRILL_DISPOSABLE": "1",
            "MIROFISH_DEPLOYMENT_ENV": "staging",
            "POSTGRES_USER": "test",
            "POSTGRES_DB": "test",
            "MIROFISH_OBJECT_STORAGE_BUCKET": "test",
        },
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "destroy-disposable-state" in result.stderr


def test_restore_refuses_production_even_with_destructive_confirmation(tmp_path: Path) -> None:
    result = subprocess.run(
        [str(INFRA / "scripts" / "restore-postgres-minio.sh")],
        env={
            **os.environ,
            "RESTORE_BACKUP_DIR": str(tmp_path),
            "RESTORE_CONFIRM": "destroy-disposable-state",
            "RESTORE_DRILL_DISPOSABLE": "1",
            "MIROFISH_DEPLOYMENT_ENV": "production",
            "POSTGRES_USER": "test",
            "POSTGRES_DB": "test",
            "MIROFISH_OBJECT_STORAGE_BUCKET": "test",
        },
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "cannot target production" in result.stderr


def test_complete_recovery_and_smtp_configuration_is_accepted_without_secret_output() -> None:
    env = _valid_config()
    result = _validate(env)
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    for secret_name in (
        "MIROFISH_AUTH_SESSION_SECRET",
        "MIROFISH_RECOVERY_CLIENT_PROOF_SECRET",
        "MIROFISH_TRUSTED_CLIENT_IP_HEADER",
        "AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY",
        "MIROFISH_RATE_LIMIT_KEY_SECRET",
        "SMTP_PASSWORD",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
    ):
        assert env[secret_name] not in output


@pytest.mark.parametrize(
    "missing",
    [
        "MIROFISH_RECOVERY_CLIENT_PROOF_SECRET",
        "MIROFISH_TRUSTED_CLIENT_IP_HEADER",
        "AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY",
        "MIROFISH_AUTH_RATE_LIMIT_REDIS_URL",
        "MIROFISH_RATE_LIMIT_KEY_SECRET",
        "MIROFISH_RATE_LIMIT_POLICIES_JSON",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_TLS_MODE",
        "AUTH_RECOVERY_RESET_BASE_URL",
        "COLLABORATION_ACCEPT_BASE_URL",
        "MIROFISH_OBJECT_STORAGE_ENDPOINT",
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
        "MIROFISH_OBJECT_STORAGE_USE_SSL",
        "MIROFISH_OBJECT_STORAGE_REGION",
    ],
)
def test_recovery_and_delivery_configuration_is_individually_required(missing: str) -> None:
    env = _valid_config()
    env.pop(missing)
    result = _validate(env)
    assert result.returncode != 0
    assert f"{missing} is required" in result.stderr


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("MIROFISH_RECOVERY_CLIENT_PROOF_SECRET", "short", "at least 32 bytes"),
        ("MIROFISH_TRUSTED_CLIENT_IP_HEADER", "X-Forwarded-For", "edge-overwritten"),
        ("AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY", "short", "decode to exactly 32 bytes"),
        ("AUTH_RECOVERY_OUTBOX_ENCRYPTION_KEY", "c3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3Nzc3M=", "must be distinct"),
        ("MIROFISH_RATE_LIMIT_KEY_SECRET", "short", "at least 32 bytes"),
        ("MIROFISH_AUTH_RATE_LIMIT_REDIS_URL", "http://redis:6379", "redis:// or rediss://"),
        ("MIROFISH_OBJECT_STORAGE_ENDPOINT", "https://minio.example.test", "host:port without a scheme"),
        ("MIROFISH_RATE_LIMIT_POLICIES_JSON", '{"auth_login":{"limit":10,"window_seconds":60}}', "missing a required policy class"),
        ("SMTP_PORT", "0", "1 to 65535"),
        ("SMTP_PORT", "not-a-port", "1 to 65535"),
        ("SMTP_FROM", "not-an-email", "email address"),
        ("AUTH_RECOVERY_RESET_BASE_URL", "http://app.example.test/reset", "must use HTTPS"),
        ("COLLABORATION_ACCEPT_BASE_URL", "https://user:pass@app.example.test/accept", "must not contain credentials"),
        ("MIROFISH_OBJECT_STORAGE_USE_SSL", "sometimes", "must be true or false"),
    ],
)
def test_recovery_and_delivery_configuration_rejects_unsafe_values(name: str, value: str, message: str) -> None:
    env = _valid_config()
    env[name] = value
    result = _validate(env)
    assert result.returncode != 0
    assert message in result.stderr


def test_config_validation_rejects_placeholders_without_echoing_secret() -> None:
    secret = "replace-with-super-secret-value"
    env = _valid_config()
    env["POSTGRES_PASSWORD"] = secret
    result = _validate(env)
    assert result.returncode != 0
    assert secret not in result.stdout + result.stderr


def test_backup_and_restore_verify_canonical_content_after_database_destruction() -> None:
    backup = (INFRA / "scripts" / "backup-postgres-minio.sh").read_text(encoding="utf-8")
    restore = (INFRA / "scripts" / "restore-postgres-minio.sh").read_text(encoding="utf-8")
    assert "TABLE_ROW_CONTENT_HASHES.before" in backup
    assert "to_jsonb(source_row)::text" in backup
    assert "PostgreSQL content changed while the dump was captured" in backup
    assert "hash_file TABLE_ROW_CONTENT_HASHES" in backup
    assert "--no-acl" not in backup
    assert "--no-acl" not in restore
    assert restore.index("DROP DATABASE IF EXISTS") < restore.index("pg_restore")
    assert "TABLE_ROW_CONTENT_HASHES" in restore
    assert "canonical table row-content hashes differ" in restore
    assert "OBJECT_SHA256_INVENTORY" in restore
    assert 'mkdir -p "$verify_objects/objects"' in restore
    assert "APP_DATABASE_PASSWORD" in restore
    assert "row_security_active('projects')" in restore
    assert "row_security_active('legacy_artifact_imports')" in restore
    assert "(SELECT count(*) FROM projects) = 0" in restore
    assert "(SELECT count(*) FROM legacy_artifact_imports) = 0" in restore
    assert "app_set_tenant_context" in restore
    assert "has_table_privilege" in restore
    assert "SELECT,INSERT,UPDATE,DELETE" in restore
    assert "$APP_DATABASE_USER|true|true|true|0" in restore
    assert "sensitive-table privilege smoke failed" in restore


def test_prometheus_alert_rules_have_firing_and_recovery_fixture() -> None:
    fixture = (INFRA / "monitoring" / "alerts_test.yml").read_text(encoding="utf-8")
    assert "api-unavailable-fires-and-recovers" in fixture
    assert "eval_time: 3m" in fixture
    assert "alertname: MiroFishApiUnavailable" in fixture
    assert "eval_time: 5m" in fixture
    assert "exp_alerts: []" in fixture


def test_bootstrap_requires_contiguous_migrations_and_multi_object_sentinels() -> None:
    migrations = sorted((INFRA / "postgres" / "migrations").glob("[0-9][0-9][0-9][0-9]_*.sql"))
    assert [int(path.name[:4]) for path in migrations] == list(range(1, len(migrations) + 1))
    bootstrap = (INFRA / "scripts" / "bootstrap-compose-database.sh").read_text(encoding="utf-8")
    assert "migration sequence gap" in bootstrap
    assert "migration sentinel incomplete" in bootstrap
    assert "migration ledger mismatch" in bootstrap
    for sentinel in (
        "app_set_tenant_context(uuid,uuid,boolean)",
        "idx_asset_embeddings_reindex_batch",
        "llm_quota_reservations",
        "trg_outline_versions_immutable",
        "manuscript_block_versions_immutable",
        "collaboration_invitation_tenant_for_token(text)",
        "auth_abuse_rate_limits",
        "manuscript_block_versions_scene_fk",
        "password_reset_delivery_outbox",
        "auth_recovery_expire(timestamptz)",
        "idx_legacy_artifact_imports_import_status",
        "tenant_isolation_legacy_artifact_imports",
        "has_table_privilege('mirofish_app', 'legacy_artifact_imports'",
        "llm_module_bindings_tenant_default_key",
        "platform_select_llm_channels",
        "platform_select_llm_models",
        "select_llm_platform_module_defaults",
        "trg_llm_platform_default_target",
        "has_table_privilege('mirofish_app', 'llm_platform_module_defaults', 'SELECT')",
    ):
        assert sentinel in bootstrap
