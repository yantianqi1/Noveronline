from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from mirofish_agents.legacy_import.objects import (
    LegacyObjectLifecycle,
    LegacyS3ObjectStore,
    ObjectOperationResult,
    object_lifecycle_from_env,
    plan_legacy_objects,
)
from mirofish_agents.legacy_import.service import LegacyImportService
from mirofish_agents.legacy_import.source import LegacySource
from mirofish_agents.temporal.legacy_import_workflow import _authorized_payload_paths


IMPORT_ID = "11111111-1111-4111-8111-111111111111"
TENANT_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_ID = "33333333-3333-4333-8333-333333333333"
SOURCE_PROJECT_ID = "legacy-project"
ACTOR_USER_ID = "44444444-4444-4444-8444-444444444444"


class MemoryStore:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.versions: dict[str, dict[str, bytes]] = {}
        self.current_versions: dict[str, str] = {}
        self.version_counter = 0
        self.fail_delete = False
        self.overwrite_on_delete: bytes | None = None

    def get(self, object_key: str) -> bytes | None:
        return self.values.get(object_key)

    def put(self, object_key: str, data: bytes, media_type: str) -> str:
        self.version_counter += 1
        version_id = f"version-{self.version_counter}"
        self.values[object_key] = data
        self.versions.setdefault(object_key, {})[version_id] = data
        self.current_versions[object_key] = version_id
        return version_id

    def delete(self, object_key: str) -> None:
        if self.fail_delete:
            raise RuntimeError("private backend detail")
        self.values.pop(object_key, None)

    def get_versioned(self, object_key: str) -> tuple[bytes | None, str | None]:
        value = self.values.get(object_key)
        if value is None:
            return None, None
        version_id = self.current_versions.get(object_key)
        return value, version_id or f"preexisting-{hashlib.sha256(value).hexdigest()}"

    def get_version(self, object_key: str, version_id: str) -> bytes | None:
        return self.versions.get(object_key, {}).get(version_id)

    def delete_version(self, object_key: str, version_id: str) -> None:
        if self.fail_delete:
            raise RuntimeError("private backend detail")
        if self.overwrite_on_delete is not None:
            self.put(object_key, self.overwrite_on_delete, "application/octet-stream")
            self.overwrite_on_delete = None
        versions = self.versions.get(object_key, {})
        versions.pop(version_id, None)
        if self.current_versions.get(object_key) == version_id:
            self.values.pop(object_key, None)
            self.current_versions.pop(object_key, None)


class MemoryLedger:
    def __init__(self) -> None:
        self.rows: dict[str, dict[str, object]] = {}
        self.fail_version_writes = 0

    def get(self, item):
        row = self.rows.get(item.object_id)
        return dict(row) if row is not None else None

    def create_pending(self, item, *, created_by_import: bool) -> bool:
        if item.object_id in self.rows:
            return False
        self.rows[item.object_id] = {
            "object_id": item.object_id,
            "object_kind": item.object_kind,
            "source_table": item.source_table,
            "artifact_kind": item.artifact_kind,
            "source_key_hash": item.source_key_hash,
            "project_name": item.project_name,
            "source_mtime": item.source_mtime,
            "legacy_synced_at": item.legacy_synced_at,
            "source_basename": item.source_basename,
            "path_hash": item.path_hash,
            "object_key": item.object_key,
            "sha256": item.sha256,
            "size_bytes": item.size_bytes,
            "media_type": item.media_type,
            "status": "metadata_only" if item.payload is None else "pending",
            "created_by_import": created_by_import and item.payload is not None,
            "created_version_id": None,
            "last_error_code": None,
        }
        return True

    def set_status(
        self,
        item,
        status: str,
        error_code: str | None = None,
        created_version_id: str | None = None,
    ) -> None:
        self.rows[item.object_id]["status"] = status
        self.rows[item.object_id]["last_error_code"] = error_code
        if created_version_id is not None:
            self.rows[item.object_id]["created_version_id"] = created_version_id

    def set_created_version(self, item, version_id: str) -> None:
        if self.fail_version_writes > 0:
            self.fail_version_writes -= 1
            raise RuntimeError("private ownership write failure")
        row = self.rows[item.object_id]
        if row["created_version_id"] is not None:
            raise RuntimeError("version ownership already recorded")
        row["created_version_id"] = version_id


def test_plan_uses_deterministic_private_keys_and_hashes_paths(tmp_path: Path) -> None:
    source, private_text, legacy_path = _source(tmp_path)

    first = plan_legacy_objects(
        source,
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        source_project_id=SOURCE_PROJECT_ID,
    )
    second = plan_legacy_objects(
        source,
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        source_project_id=SOURCE_PROJECT_ID,
    )

    assert first == second
    assert {item.object_kind for item in first} == {"archive_source", "project_artifact"}
    for item in first:
        assert item.object_key.startswith(
            f"projects/{PROJECT_ID}/legacy-imports/{IMPORT_ID}/{item.object_kind}/"
        )
        assert private_text not in item.object_key
        assert legacy_path not in item.object_key
        assert len(item.source_key_hash) == 64
        assert len(item.sha256) == 64
    archive = next(item for item in first if item.object_kind == "archive_source")
    assert archive.path_hash is not None
    assert legacy_path not in json.dumps(archive.public_dict(), sort_keys=True)


def test_archive_source_unix_epoch_mtime_is_normalized_to_utc(tmp_path: Path) -> None:
    source, _, _ = _source(tmp_path)
    with sqlite3.connect(source.sqlite_path) as connection:
        connection.execute("UPDATE archive_sources SET file_mtime = ?", (1780888497.6818,))

    archive = next(item for item in _plan(source) if item.object_kind == "archive_source")

    assert archive.source_mtime == datetime.fromtimestamp(1780888497.6818, tz=timezone.utc)


@pytest.mark.parametrize("invalid", ["NaN", "Infinity", "-Infinity"])
def test_archive_source_non_finite_epoch_mtime_fails_closed(
    tmp_path: Path, invalid: str
) -> None:
    source, _, _ = _source(tmp_path)
    with sqlite3.connect(source.sqlite_path) as connection:
        connection.execute("UPDATE archive_sources SET file_mtime = ?", (invalid,))

    with pytest.raises(RuntimeError, match="LEGACY_ARCHIVE_SOURCE_METADATA_INVALID"):
        _plan(source)


def test_apply_verify_and_rollback_are_idempotent(tmp_path: Path) -> None:
    source, _, _ = _source(tmp_path)
    items = _plan(source)
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)

    applied = lifecycle.apply(items)
    replayed = lifecycle.apply(items)
    verified = lifecycle.verify(items)
    rolled_back = lifecycle.rollback(items)
    replayed_rollback = lifecycle.rollback(items)

    assert applied.status == "complete"
    assert applied.counts["imported"] == len(items)
    assert replayed.counts["unchanged"] == len(items)
    assert verified.counts["unchanged"] == len(items)
    assert rolled_back.counts["rolled_back"] == len(items)
    assert replayed_rollback.counts["unchanged"] == len(items)
    assert store.values == {}
    assert {row["status"] for row in ledger.rows.values()} == {"deleted"}


def test_matching_preexisting_object_is_never_deleted(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    store.values[item.object_key] = item.payload
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)

    assert lifecycle.apply([item]).status == "complete"
    assert ledger.rows[item.object_id]["created_by_import"] is False
    assert lifecycle.rollback([item]).status == "complete"
    assert store.values[item.object_key] == item.payload


def test_content_conflict_fails_closed_without_overwrite(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    store.values[item.object_key] = b"different"
    lifecycle = LegacyObjectLifecycle(store, MemoryLedger())

    result = lifecycle.apply([item])

    assert result.status == "failed"
    assert result.blockers == ("LEGACY_OBJECT_CONTENT_CONFLICT",)
    assert store.values[item.object_key] == b"different"


def test_partial_object_batch_marks_successful_writes_orphaned(tmp_path: Path) -> None:
    items = _plan(_source(tmp_path)[0])
    store = MemoryStore()
    ledger = MemoryLedger()
    store.values[items[0].object_key] = b"different"
    lifecycle = LegacyObjectLifecycle(store, ledger)

    result = lifecycle.apply(items)

    assert result.status == "failed"
    assert result.counts["conflict"] == 1
    assert result.counts["orphaned"] == 1
    successful = items[1]
    assert ledger.rows[successful.object_id]["status"] == "orphaned"
    assert ledger.rows[successful.object_id]["last_error_code"] == (
        "LEGACY_OBJECT_BATCH_APPLY_FAILED"
    )


def test_version_ownership_write_failure_compensates_exact_put(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    ledger = MemoryLedger()
    ledger.fail_version_writes = 1
    lifecycle = LegacyObjectLifecycle(store, ledger)

    result = lifecycle.apply([item])

    assert result.status == "failed"
    assert result.blockers == ("LEGACY_OBJECT_VERSION_OWNERSHIP_WRITE_FAILED",)
    assert item.object_key not in store.values
    assert ledger.rows[item.object_id]["created_version_id"] is None


def test_failed_delete_compensation_retries_durable_version_ownership(
    tmp_path: Path,
) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    store.fail_delete = True
    ledger = MemoryLedger()
    ledger.fail_version_writes = 2
    lifecycle = LegacyObjectLifecycle(store, ledger)

    result = lifecycle.apply([item])

    assert result.status == "failed"
    assert result.blockers == (
        "LEGACY_OBJECT_VERSION_OWNERSHIP_COMPENSATION_FAILED",
    )
    assert ledger.rows[item.object_id]["created_version_id"] is None
    assert ledger.rows[item.object_id]["status"] == "orphaned"
    assert item.object_key in store.values

    store.fail_delete = False
    replay = lifecycle.apply([item])

    assert replay.status == "failed"
    assert replay.blockers == ("LEGACY_OBJECT_OWNED_VERSION_MISSING",)
    version_id = store.current_versions[item.object_key]
    reconciled = lifecycle.reconcile_version(
        [item], object_id=item.object_id, version_id=version_id
    )
    replay = lifecycle.apply([item])

    assert reconciled.status == "complete"
    assert replay.status == "complete"
    assert replay.counts["unchanged"] == 1
    assert ledger.rows[item.object_id]["created_version_id"] is not None
    assert ledger.rows[item.object_id]["status"] == "verified"


def test_retry_never_guesses_same_content_current_version_ownership(
    tmp_path: Path,
) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    store.fail_delete = True
    ledger = MemoryLedger()
    ledger.fail_version_writes = 2
    lifecycle = LegacyObjectLifecycle(store, ledger)
    assert lifecycle.apply([item]).status == "failed"
    original_version = store.current_versions[item.object_key]
    replacement_version = store.put(item.object_key, item.payload, item.media_type)
    store.fail_delete = False

    replay = lifecycle.apply([item])

    assert replay.status == "failed"
    assert replay.blockers == ("LEGACY_OBJECT_OWNED_VERSION_MISSING",)
    assert ledger.rows[item.object_id]["created_version_id"] is None
    assert original_version in store.versions[item.object_key]
    assert replacement_version in store.versions[item.object_key]


def test_delete_failure_persists_orphaned_and_report_is_private(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)
    assert lifecycle.apply([item]).status == "complete"
    store.fail_delete = True

    result = lifecycle.rollback([item])
    public = json.dumps(result.public_dict(), sort_keys=True)

    assert result.status == "partial"
    assert result.counts["orphaned"] == 1
    assert ledger.rows[item.object_id]["status"] == "orphaned"
    assert item.object_key not in public
    assert item.payload.decode("utf-8", errors="ignore") not in public
    assert "private backend detail" not in public


def test_modified_current_version_survives_owned_version_rollback(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)
    assert lifecycle.apply([item]).status == "complete"
    store.put(item.object_key, b"modified after import", "application/octet-stream")

    result = lifecycle.rollback([item])

    assert result.status == "complete"
    assert store.values[item.object_key] == b"modified after import"
    assert ledger.rows[item.object_id]["status"] == "deleted"


def test_corrupted_owned_version_blocks_rollback(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)
    assert lifecycle.apply([item]).status == "complete"
    imported_version = ledger.rows[item.object_id]["created_version_id"]
    store.versions[item.object_key][imported_version] = b"corrupted owned version"

    result = lifecycle.rollback([item])

    assert result.status == "partial"
    assert result.blockers == ("LEGACY_OBJECT_CONTENT_CONFLICT",)
    assert imported_version in store.versions[item.object_key]


def test_concurrent_overwrite_survives_versioned_rollback(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)
    assert lifecycle.apply([item]).status == "complete"
    store.overwrite_on_delete = b"concurrent replacement"

    result = lifecycle.rollback([item])

    assert result.status == "complete"
    assert store.values[item.object_key] == b"concurrent replacement"
    assert ledger.rows[item.object_id]["status"] == "deleted"


def test_same_content_new_version_is_not_owned_or_deleted(tmp_path: Path) -> None:
    item = _plan(_source(tmp_path)[0])[0]
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)
    assert lifecycle.apply([item]).status == "complete"
    imported_version = ledger.rows[item.object_id]["created_version_id"]
    replacement_version = store.put(item.object_key, item.payload, item.media_type)

    result = lifecycle.rollback([item])

    assert result.status == "complete"
    assert replacement_version != imported_version
    assert store.values[item.object_key] == item.payload
    assert imported_version not in store.versions[item.object_key]
    assert replacement_version in store.versions[item.object_key]


def test_target_failure_marks_only_import_created_objects_as_orphaned(tmp_path: Path) -> None:
    items = _plan(_source(tmp_path)[0])
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)
    store.values[items[0].object_key] = items[0].payload
    assert lifecycle.apply(items).status == "complete"

    result = lifecycle.orphan(items)

    assert result.status == "partial"
    assert "LEGACY_OBJECT_TARGET_APPLY_FAILED" in result.blockers
    assert ledger.rows[items[0].object_id]["status"] == "verified"
    created = [item for item in items if item.object_id != items[0].object_id]
    assert created
    assert all(ledger.rows[item.object_id]["status"] == "orphaned" for item in created)


def test_target_failure_does_not_orphan_objects_from_prior_committed_replay(tmp_path: Path) -> None:
    items = _plan(_source(tmp_path)[0])
    store = MemoryStore()
    ledger = MemoryLedger()
    lifecycle = LegacyObjectLifecycle(store, ledger)
    assert lifecycle.apply(items).status == "complete"

    replay = lifecycle.apply(items)
    orphaned = lifecycle.orphan(items, only_object_ids=set(replay.staged_object_ids))

    assert replay.staged_object_ids == ()
    assert orphaned.counts["orphaned"] == 0
    assert {row["status"] for row in ledger.rows.values()} == {"verified"}


@pytest.mark.parametrize("archive_path", ["../outside.txt", "/private/legacy.txt", "C:\\private\\legacy.txt"])
def test_unmapped_archive_path_is_metadata_only_without_object_store_calls(
    tmp_path: Path, archive_path: str
) -> None:
    source, _, _ = _source(tmp_path, archive_path=archive_path)
    (tmp_path / "outside.txt").write_text("outside", encoding="utf-8")
    items = _plan(source)
    metadata = next(item for item in items if item.object_kind == "archive_source")
    store = MemoryStore()
    lifecycle = LegacyObjectLifecycle(store, MemoryLedger())

    assert metadata.payload is None
    assert metadata.object_key is None
    assert metadata.sha256 is None
    assert metadata.size_bytes is None
    assert metadata.unsupported_reason == "APPROVED_LEGACY_SOURCE_PATH_UNSUPPORTED"
    applied = lifecycle.apply([metadata])
    verified = lifecycle.verify([metadata])
    rolled_back = lifecycle.rollback([metadata])
    assert applied.status == "complete"
    assert applied.counts["metadata_only"] == 1
    assert verified.counts["metadata_only"] == 1
    assert rolled_back.counts["rolled_back"] == 1
    assert store.values == {}


def test_object_env_is_all_or_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "MIROFISH_OBJECT_STORAGE_ENDPOINT",
        "MIROFISH_OBJECT_STORAGE_BUCKET",
        "MIROFISH_OBJECT_STORAGE_ACCESS_KEY",
        "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    assert object_lifecycle_from_env("postgresql://unused") is None
    monkeypatch.setenv("MIROFISH_OBJECT_STORAGE_ENDPOINT", "minio:9000")
    with pytest.raises(RuntimeError, match="configuration is incomplete"):
        object_lifecycle_from_env("postgresql://unused")


def test_version_delete_request_signs_exact_object_version() -> None:
    store = LegacyS3ObjectStore(
        endpoint="minio.example.test:9000",
        bucket="private-bucket",
        access_key="test-access",
        secret_key="test-secret",
        use_ssl=True,
    )

    request = store._signed_version_delete("private/object.json", "version+one")

    assert request.full_url == (
        "https://minio.example.test:9000/private-bucket/private/object.json"
        "?versionId=version%2Bone"
    )
    assert request.method == "DELETE"
    assert request.get_header("Authorization").startswith("AWS4-HMAC-SHA256 ")
    assert "version+one" not in request.get_header("Authorization")


def test_service_reconciles_approved_metadata_only_source_and_requires_lifecycle(
    tmp_path: Path,
) -> None:
    source, _, _ = _source(tmp_path, archive_path="../outside.txt")
    service = LegacyImportService(
        source_path=str(source.sqlite_path),
        artifact_root=str(source.artifact_root),
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        actor_user_id=ACTOR_USER_ID,
        source_project_id=SOURCE_PROJECT_ID,
        target_dsn="postgresql://unused",
    )

    plan = service.plan()
    report = service.plan_report()
    failed_reports = [
        service.apply(
            execute=True,
            expected_source_fingerprint=plan.source.fingerprint,
            expected_plan_hash=plan.plan_hash,
        ),
        service.verify(
            expected_source_fingerprint=plan.source.fingerprint,
            expected_plan_hash=plan.plan_hash,
        ),
        service.rollback(
            execute=True,
            expected_source_fingerprint=plan.source.fingerprint,
            expected_plan_hash=plan.plan_hash,
        ),
    ]

    assert plan.families["source"].deferred_count == 0
    assert plan.families["source"].unsupported_count == 1
    assert plan.families["source"].reason_codes == [
        "APPROVED_LEGACY_SOURCE_PATH_UNSUPPORTED"
    ]
    assert report["object_counts"] == {
        "planned": 2,
        "uploadable": 1,
        "metadata_only": 1,
    }
    assert "OBJECT_STORAGE_DESTINATION_REQUIRED" not in json.dumps(report)
    encoded_reports = json.dumps({"plan": report, "failed": failed_reports}, sort_keys=True)
    assert "Private Project" not in encoded_reports
    assert "../outside.txt" not in encoded_reports
    assert "private novel content" not in encoded_reports
    assert {report["operation"] for report in failed_reports} == {
        "apply",
        "verify",
        "rollback",
    }
    for failed in failed_reports:
        assert failed["status"] == "failed"
        assert "LEGACY_OBJECT_LIFECYCLE_REQUIRED" in failed["blockers"]


def test_invalid_project_artifact_json_fails_closed_during_plan(tmp_path: Path) -> None:
    source, _, _ = _source(tmp_path)
    with sqlite3.connect(source.sqlite_path) as connection:
        connection.execute("UPDATE project_artifacts SET payload_json = 'not-json'")
    service = LegacyImportService(
        source_path=str(source.sqlite_path),
        artifact_root=str(source.artifact_root),
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        actor_user_id=ACTOR_USER_ID,
        source_project_id=SOURCE_PROJECT_ID,
    )

    with pytest.raises(RuntimeError, match="LEGACY_ARTIFACT_PAYLOAD_INVALID"):
        service.plan()


def test_temporal_source_paths_are_scoped_to_read_only_import_root(tmp_path: Path) -> None:
    root = tmp_path / "source-root"
    root.mkdir()
    database = root / "legacy.db"
    database.write_bytes(b"sqlite-placeholder")
    artifacts = root / "artifacts"
    artifacts.mkdir()

    scoped = _authorized_payload_paths(
        {"source_path": "legacy.db", "artifact_root": "artifacts"}, str(root)
    )

    assert scoped["source_path"] == str(database)
    assert scoped["artifact_root"] == str(artifacts)
    with pytest.raises(RuntimeError, match="outside the authorized root"):
        _authorized_payload_paths(
            {"source_path": "../outside.db", "artifact_root": None}, str(root)
        )
    with pytest.raises(RuntimeError, match="LEGACY_IMPORT_SOURCE_ROOT is required"):
        _authorized_payload_paths({"source_path": str(database)}, "")
    source_link = root / "linked.db"
    source_link.symlink_to(database)
    with pytest.raises(RuntimeError, match="source symlinks are unsupported"):
        _authorized_payload_paths(
            {"source_path": "linked.db", "artifact_root": None}, str(root)
        )


def test_artifact_inspection_rejects_symlink_escape(tmp_path: Path) -> None:
    source, _, _ = _source(tmp_path)
    outside = tmp_path / "outside-private.txt"
    outside.write_text("outside private content", encoding="utf-8")
    (source.artifact_root / "escape.txt").symlink_to(outside)

    with pytest.raises(RuntimeError, match="LEGACY_ARTIFACT_SYMLINK_UNSUPPORTED"):
        source.inspect()


def test_legacy_source_rejects_direct_database_symlink(tmp_path: Path) -> None:
    source, _, _ = _source(tmp_path)
    linked = tmp_path / "linked-legacy.db"
    linked.symlink_to(source.sqlite_path)

    with pytest.raises(RuntimeError, match="source database symlinks are unsupported"):
        LegacySource(linked)


def test_temporal_plan_binding_is_required_and_rejects_changed_source(
    tmp_path: Path,
) -> None:
    source, _, _ = _source(tmp_path)
    service = LegacyImportService(
        source_path=str(source.sqlite_path),
        artifact_root=str(source.artifact_root),
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        actor_user_id=ACTOR_USER_ID,
        source_project_id=SOURCE_PROJECT_ID,
        target_dsn="postgresql://must-not-connect",
    )
    plan = service.plan()

    missing = service.apply(
        execute=True,
        expected_source_fingerprint="",
        expected_plan_hash="",
    )
    changed = service.apply(
        execute=True,
        expected_source_fingerprint="changed-source",
        expected_plan_hash=plan.plan_hash,
    )

    assert "LEGACY_IMPORT_PLAN_BINDING_REQUIRED" in missing["blockers"]
    assert "LEGACY_IMPORT_PLAN_CHANGED" in changed["blockers"]


def test_snapshot_rejects_source_change_after_object_payload_read(
    tmp_path: Path,
) -> None:
    source, _, _ = _source(tmp_path)
    service = LegacyImportService(
        source_path=str(source.sqlite_path),
        artifact_root=str(source.artifact_root),
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        actor_user_id=ACTOR_USER_ID,
        source_project_id=SOURCE_PROJECT_ID,
    )
    original = service._planned_objects

    def mutate_after_read():
        objects = original()
        with sqlite3.connect(source.sqlite_path) as connection:
            connection.execute(
                "INSERT INTO project_artifacts VALUES (?, 'changed', '{}')",
                (SOURCE_PROJECT_ID,),
            )
        return objects

    service._planned_objects = mutate_after_read  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="SOURCE_CHANGED_DURING_PLAN"):
        service.plan()


def test_public_result_contains_counts_and_codes_only() -> None:
    result = ObjectOperationResult(
        "partial",
        {"planned": 1, "orphaned": 1},
        ("LEGACY_OBJECT_DELETE_FAILED",),
    )
    assert result.public_dict() == {
        "status": "partial",
        "object_counts": {"orphaned": 1, "planned": 1},
        "blockers": ["LEGACY_OBJECT_DELETE_FAILED"],
        "object_reasons": [],
    }


def _plan(source: LegacySource):
    return plan_legacy_objects(
        source,
        import_id=IMPORT_ID,
        tenant_id=TENANT_ID,
        project_id=PROJECT_ID,
        source_project_id=SOURCE_PROJECT_ID,
    )


def _source(
    tmp_path: Path, *, archive_path: str = "uploads/novel.txt"
) -> tuple[LegacySource, str, str]:
    database = tmp_path / f"legacy-{uuid.uuid4()}.db"
    artifact_root = tmp_path / f"artifacts-{uuid.uuid4()}"
    artifact_root.mkdir()
    private_text = "private novel content"
    if (
        not archive_path.startswith("..")
        and not Path(archive_path).is_absolute()
        and not (len(archive_path) >= 3 and archive_path[1:3] in {":\\", ":/"})
    ):
        target = artifact_root / archive_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(private_text, encoding="utf-8")
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE project_artifacts (
              project_id TEXT NOT NULL,
              artifact_key TEXT NOT NULL,
              payload_json TEXT NOT NULL
            );
            CREATE TABLE archive_sources (
              project_id TEXT NOT NULL,
              project_name TEXT,
              file_path TEXT NOT NULL,
              file_mtime TEXT,
              synced_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO project_artifacts VALUES (?, ?, ?)",
            (SOURCE_PROJECT_ID, "seed_analysis", json.dumps({"text": private_text})),
        )
        connection.execute(
            "INSERT INTO archive_sources VALUES (?, ?, ?, ?, ?)",
            (
                SOURCE_PROJECT_ID,
                "Private Project",
                archive_path,
                "2026-01-02T03:04:05+00:00",
                "2026-01-02T04:05:06+00:00",
            ),
        )
    return LegacySource(database, artifact_root), private_text, archive_path
