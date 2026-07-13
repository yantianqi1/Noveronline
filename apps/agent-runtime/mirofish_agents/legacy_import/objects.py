from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from psycopg.rows import dict_row

from mirofish_agents.temporal.seed import S3CompatibleObjectStore

from .source import LegacySource


OBJECT_ENV_NAMES = (
    "MIROFISH_OBJECT_STORAGE_ENDPOINT",
    "MIROFISH_OBJECT_STORAGE_BUCKET",
    "MIROFISH_OBJECT_STORAGE_ACCESS_KEY",
    "MIROFISH_OBJECT_STORAGE_SECRET_KEY",
)
OBJECT_STATUSES = frozenset(
    {"pending", "verified", "metadata_only", "delete_pending", "orphaned", "deleted"}
)


class LegacyObjectStore(Protocol):
    def get(self, object_key: str) -> bytes | None: ...

    def put(self, object_key: str, data: bytes, media_type: str) -> str: ...

    def get_versioned(self, object_key: str) -> tuple[bytes | None, str | None]: ...

    def get_version(self, object_key: str, version_id: str) -> bytes | None: ...

    def delete_version(self, object_key: str, version_id: str) -> None: ...


@dataclass(frozen=True)
class PlannedLegacyObject:
    object_id: str
    tenant_id: str
    project_id: str
    import_id: str
    object_kind: str
    source_table: str
    artifact_kind: str
    source_key_hash: str
    project_name: str | None
    source_mtime: datetime | None
    legacy_synced_at: datetime | None
    source_basename: str | None
    path_hash: str | None
    object_key: str | None
    sha256: str | None
    size_bytes: int | None
    media_type: str | None
    payload: bytes | None
    unsupported_reason: str | None = None

    def public_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "object_kind": self.object_kind,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "metadata_only": self.payload is None,
        }


@dataclass(frozen=True)
class ObjectOperationResult:
    status: str
    counts: dict[str, int]
    blockers: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    staged_object_ids: tuple[str, ...] = ()

    def public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "object_counts": dict(sorted(self.counts.items())),
            "blockers": sorted(set(self.blockers)),
            "object_reasons": sorted(set(self.reasons)),
        }


class LegacyS3ObjectStore(S3CompatibleObjectStore):
    """S3-compatible store using the runtime's SigV4 implementation."""

    def get(self, object_key: str) -> bytes | None:
        try:
            return self.read_bytes(object_key)
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def put(self, object_key: str, data: bytes, media_type: str) -> str:
        request = self._signed_request("PUT", object_key, data, media_type)
        with urlopen(request, timeout=30) as response:
            version_id = response.headers.get("x-amz-version-id")
            if not version_id or version_id == "null":
                raise RuntimeError("legacy object bucket versioning is required")
            return version_id

    def get_versioned(self, object_key: str) -> tuple[bytes | None, str | None]:
        request = self._signed_request("GET", object_key, b"", None)
        try:
            with urlopen(request, timeout=30) as response:
                version_id = response.headers.get("x-amz-version-id")
                if not version_id or version_id == "null":
                    return response.read(), None
                return response.read(), version_id
        except HTTPError as exc:
            if exc.code == 404:
                return None, None
            raise

    def delete_version(self, object_key: str, version_id: str) -> None:
        request = self._signed_version_request("DELETE", object_key, version_id)
        with urlopen(request, timeout=30):
            return

    def _signed_version_delete(self, object_key: str, version_id: str) -> Request:
        return self._signed_version_request("DELETE", object_key, version_id)

    def get_version(self, object_key: str, version_id: str) -> bytes | None:
        request = self._signed_version_request("GET", object_key, version_id)
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def _signed_version_request(
        self, method: str, object_key: str, version_id: str
    ) -> Request:
        if method not in {"GET", "DELETE"}:
            raise ValueError("version request method is not allowed")
        normalized_key = object_key.strip()
        normalized_version = version_id.strip()
        if not normalized_key or not normalized_version:
            raise ValueError("object key and version id are required")
        encoded_path = f"/{quote(self.bucket, safe='')}/{quote(normalized_key, safe='/')}"
        canonical_query = f"versionId={quote(normalized_version, safe='-_.~')}"
        now = datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")
        payload_hash = hashlib.sha256(b"").hexdigest()
        host = self.endpoint_url.split("://", 1)[1]
        headers = {
            "host": host,
            "x-amz-content-sha256": payload_hash,
            "x-amz-date": amz_date,
        }
        canonical_headers = "".join(f"{key}:{headers[key]}\n" for key in sorted(headers))
        signed_headers = ";".join(sorted(headers))
        canonical_request = "\n".join(
            [
                method,
                encoded_path,
                canonical_query,
                canonical_headers,
                signed_headers,
                payload_hash,
            ]
        )
        credential_scope = f"{date_stamp}/{self._region}/s3/aws4_request"
        string_to_sign = "\n".join(
            [
                "AWS4-HMAC-SHA256",
                amz_date,
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        signing_key = _aws_signing_key(
            self._secret_key, date_stamp, self._region
        )
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        authorization = (
            "AWS4-HMAC-SHA256 "
            f"Credential={self._access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return Request(
            f"{self.endpoint_url}{encoded_path}?{canonical_query}",
            data=None if method == "GET" else b"",
            headers={
                "Authorization": authorization,
                "Host": host,
                "X-Amz-Content-Sha256": payload_hash,
                "X-Amz-Date": amz_date,
            },
            method=method,
        )


class PostgresLegacyObjectLedger:
    def __init__(self, connect: Callable[[], Any]) -> None:
        self.connect = connect

    @classmethod
    def from_dsn(cls, dsn: str) -> "PostgresLegacyObjectLedger":
        import psycopg

        return cls(lambda: psycopg.connect(dsn, row_factory=dict_row))

    def get(self, item: PlannedLegacyObject) -> dict[str, Any] | None:
        with self.connect() as connection:
            self._set_context(connection, item)
            return connection.execute(
                """
                SELECT object_id::text, object_kind, source_table, artifact_kind,
                       source_key_hash, project_name, source_mtime, legacy_synced_at,
                       source_basename, path_hash, object_key, sha256, size_bytes,
                       media_type, status, created_by_import, created_version_id
                FROM legacy_artifact_imports
                WHERE tenant_id = %s::uuid AND import_id = %s::uuid AND object_id = %s::uuid
                """,
                (item.tenant_id, item.import_id, item.object_id),
            ).fetchone()

    def create_pending(self, item: PlannedLegacyObject, *, created_by_import: bool) -> bool:
        with self.connect() as connection:
            self._set_context(connection, item)
            inserted = connection.execute(
                """
                INSERT INTO legacy_artifact_imports (
                    tenant_id, object_id, import_id, project_id, object_kind,
                    source_table, artifact_kind, source_key_hash, project_name,
                    source_mtime, legacy_synced_at, source_basename, path_hash,
                    object_key, sha256, size_bytes, media_type, status, created_by_import
                ) VALUES (
                    %s::uuid, %s::uuid, %s::uuid, %s::uuid, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s
                ) ON CONFLICT (tenant_id, import_id, object_id) DO NOTHING
                RETURNING object_id
                """,
                (
                    item.tenant_id,
                    item.object_id,
                    item.import_id,
                    item.project_id,
                    item.object_kind,
                    item.source_table,
                    item.artifact_kind,
                    item.source_key_hash,
                    item.project_name,
                    item.source_mtime,
                    item.legacy_synced_at,
                    item.source_basename,
                    item.path_hash,
                    item.object_key,
                    item.sha256,
                    item.size_bytes,
                    item.media_type,
                    "metadata_only" if item.payload is None else "pending",
                    created_by_import and item.payload is not None,
                ),
            ).fetchone()
            return inserted is not None

    def set_status(
        self,
        item: PlannedLegacyObject,
        status: str,
        error_code: str | None = None,
        created_version_id: str | None = None,
    ) -> None:
        if status not in OBJECT_STATUSES:
            raise ValueError("invalid legacy object status")
        with self.connect() as connection:
            self._set_context(connection, item)
            cursor = connection.execute(
                """
                UPDATE legacy_artifact_imports
                SET status = %s, last_error_code = %s, updated_at = now(),
                    created_version_id = COALESCE(%s, created_version_id),
                    verified_at = CASE WHEN %s = 'verified' THEN now() ELSE verified_at END,
                    deleted_at = CASE WHEN %s = 'deleted' THEN now() ELSE deleted_at END
                WHERE tenant_id = %s::uuid AND import_id = %s::uuid AND object_id = %s::uuid
                """,
                (
                    status,
                    error_code,
                    created_version_id,
                    status,
                    status,
                    item.tenant_id,
                    item.import_id,
                    item.object_id,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("legacy object ledger row is missing")

    def set_created_version(
        self, item: PlannedLegacyObject, version_id: str
    ) -> None:
        if not version_id.strip():
            raise ValueError("legacy object version id is required")
        with self.connect() as connection:
            self._set_context(connection, item)
            cursor = connection.execute(
                """
                UPDATE legacy_artifact_imports
                SET created_version_id = %s, updated_at = now()
                WHERE tenant_id = %s::uuid
                  AND import_id = %s::uuid
                  AND object_id = %s::uuid
                  AND created_by_import
                  AND created_version_id IS NULL
                """,
                (version_id, item.tenant_id, item.import_id, item.object_id),
            )
            if cursor.rowcount != 1:
                raise RuntimeError("legacy object version ownership write failed")

    @staticmethod
    def _set_context(connection: Any, item: PlannedLegacyObject) -> None:
        connection.execute(
            "SELECT app_set_tenant_context(%s::uuid, NULL, false)",
            (item.tenant_id,),
        )


class LegacyObjectLifecycle:
    def __init__(self, store: LegacyObjectStore, ledger: Any) -> None:
        self.store = store
        self.ledger = ledger

    def apply(self, items: list[PlannedLegacyObject]) -> ObjectOperationResult:
        counts = _counts(planned=len(items))
        blockers: list[str] = []
        reasons = _unsupported_reasons(items)
        staged_object_ids: set[str] = set()
        for item in items:
            try:
                row = self.ledger.get(item)
                if item.payload is None:
                    if row is None:
                        self.ledger.create_pending(item, created_by_import=False)
                        row = self.ledger.get(item)
                    if row is None:
                        raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_MISSING")
                    _validate_row(item, row)
                    if row["status"] == "deleted":
                        raise LegacyObjectConflict("LEGACY_OBJECT_ALREADY_ROLLED_BACK")
                    if row["status"] != "metadata_only":
                        raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_CONFLICT")
                    counts["metadata_only"] += 1
                    continue
                object_key, payload, media_type = _required_object_values(item)
                existing = self.store.get(object_key)
                created_version_id: str | None = None
                if row is not None:
                    _validate_row(item, row)
                    if row["status"] == "deleted":
                        raise LegacyObjectConflict("LEGACY_OBJECT_ALREADY_ROLLED_BACK")
                    if existing is None and row["status"] in {"verified", "delete_pending"}:
                        raise LegacyObjectConflict("LEGACY_OBJECT_MISSING")
                    created = bool(row["created_by_import"])
                    created_version_id = row.get("created_version_id")
                    if created and created_version_id:
                        owned = self.store.get_version(object_key, created_version_id)
                        if owned is None:
                            raise LegacyObjectConflict("LEGACY_OBJECT_OWNED_VERSION_MISSING")
                        _validate_payload(item, owned)
                        self.ledger.set_status(item, "verified")
                        counts["unchanged"] += 1
                        continue
                    if created and row["status"] in {"pending", "orphaned"}:
                        staged_object_ids.add(item.object_id)
                else:
                    if existing is not None:
                        _validate_payload(item, existing)
                    created = existing is None
                    if not self.ledger.create_pending(item, created_by_import=created):
                        row = self.ledger.get(item)
                        if row is None:
                            raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_RACE")
                        _validate_row(item, row)
                        created = bool(row["created_by_import"])
                    elif created:
                        staged_object_ids.add(item.object_id)
                if existing is None:
                    created_version_id = self.store.put(object_key, payload, media_type)
                    try:
                        self.ledger.set_created_version(item, created_version_id)
                    except Exception as ownership_error:
                        try:
                            self.store.delete_version(object_key, created_version_id)
                        except Exception as compensation_error:
                            try:
                                self.ledger.set_created_version(item, created_version_id)
                            except Exception:
                                pass
                            raise LegacyObjectConflict(
                                "LEGACY_OBJECT_VERSION_OWNERSHIP_COMPENSATION_FAILED"
                            ) from compensation_error
                        raise LegacyObjectConflict(
                            "LEGACY_OBJECT_VERSION_OWNERSHIP_WRITE_FAILED"
                        ) from ownership_error
                elif created and not created_version_id:
                    raise LegacyObjectConflict("LEGACY_OBJECT_OWNED_VERSION_MISSING")
                stored = self.store.get(object_key)
                if stored is None:
                    raise LegacyObjectConflict("LEGACY_OBJECT_PUT_NOT_VISIBLE")
                _validate_payload(item, stored)
                self.ledger.set_status(item, "verified")
                counts["imported" if created and existing is None else "unchanged"] += 1
            except LegacyObjectConflict as exc:
                counts["conflict"] += 1
                blockers.append(exc.code)
            except Exception:
                counts["conflict"] += 1
                blockers.append("LEGACY_OBJECT_APPLY_FAILED")
                self._mark_orphaned(item, "LEGACY_OBJECT_APPLY_FAILED")
        if blockers:
            counts["orphaned"] += self._mark_batch_orphans(items, staged_object_ids)
        status = "failed" if blockers else "complete"
        return ObjectOperationResult(
            status,
            counts,
            tuple(blockers),
            reasons,
            tuple(sorted(staged_object_ids)),
        )

    def verify(self, items: list[PlannedLegacyObject]) -> ObjectOperationResult:
        counts = _counts(planned=len(items))
        blockers: list[str] = []
        reasons = _unsupported_reasons(items)
        for item in items:
            try:
                row = self.ledger.get(item)
                if row is None:
                    raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_MISSING")
                _validate_row(item, row)
                if item.payload is None:
                    if row["status"] != "metadata_only":
                        raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_CONFLICT")
                    counts["metadata_only"] += 1
                    continue
                if row["status"] not in {"verified", "delete_pending"}:
                    raise LegacyObjectConflict("LEGACY_OBJECT_NOT_VERIFIED")
                object_key, _, _ = _required_object_values(item)
                if bool(row["created_by_import"]):
                    version_id = row.get("created_version_id")
                    if not version_id:
                        raise LegacyObjectConflict("LEGACY_OBJECT_OWNED_VERSION_MISSING")
                    stored = self.store.get_version(object_key, version_id)
                else:
                    stored = self.store.get(object_key)
                if stored is None:
                    raise LegacyObjectConflict("LEGACY_OBJECT_MISSING")
                _validate_payload(item, stored)
                self.ledger.set_status(item, "verified")
                counts["unchanged"] += 1
            except LegacyObjectConflict as exc:
                counts["conflict"] += 1
                blockers.append(exc.code)
            except Exception:
                counts["conflict"] += 1
                blockers.append("LEGACY_OBJECT_VERIFY_FAILED")
        status = "failed" if blockers else "complete"
        return ObjectOperationResult(status, counts, tuple(blockers), reasons)

    def rollback(self, items: list[PlannedLegacyObject]) -> ObjectOperationResult:
        counts = _counts(planned=len(items))
        blockers: list[str] = []
        for item in reversed(items):
            try:
                row = self.ledger.get(item)
                if row is None or row["status"] == "deleted":
                    counts["unchanged"] += 1
                    continue
                _validate_row(item, row)
                if item.payload is None:
                    if row["status"] != "metadata_only":
                        raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_CONFLICT")
                    self.ledger.set_status(item, "deleted")
                    counts["rolled_back"] += 1
                    continue
                self.ledger.set_status(item, "delete_pending")
                object_key, _, _ = _required_object_values(item)
                if bool(row["created_by_import"]):
                    version_id = row.get("created_version_id")
                    if not version_id:
                        raise LegacyObjectConflict("LEGACY_OBJECT_OWNED_VERSION_MISSING")
                    stored = self.store.get_version(object_key, version_id)
                    if stored is None:
                        raise LegacyObjectConflict("LEGACY_OBJECT_OWNED_VERSION_MISSING")
                    _validate_payload(item, stored)
                    self.store.delete_version(object_key, version_id)
                self.ledger.set_status(item, "deleted")
                counts["rolled_back"] += 1
            except LegacyObjectConflict as exc:
                counts["orphaned"] += 1
                blockers.append(exc.code)
                self._mark_orphaned(item, exc.code)
            except Exception:
                counts["orphaned"] += 1
                blockers.append("LEGACY_OBJECT_DELETE_FAILED")
                self._mark_orphaned(item, "LEGACY_OBJECT_DELETE_FAILED")
        reasons = _unsupported_reasons(items)
        return ObjectOperationResult(
            "partial" if blockers else "complete", counts, tuple(blockers), reasons
        )

    def reconcile_version(
        self,
        items: list[PlannedLegacyObject],
        *,
        object_id: str,
        version_id: str,
    ) -> ObjectOperationResult:
        counts = _counts(planned=len(items))
        item = next((candidate for candidate in items if candidate.object_id == object_id), None)
        if item is None or item.payload is None or item.object_key is None:
            return ObjectOperationResult(
                "failed", counts, ("LEGACY_OBJECT_RECONCILE_TARGET_INVALID",)
            )
        try:
            row = self.ledger.get(item)
            if row is None:
                raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_MISSING")
            _validate_row(item, row)
            if not bool(row["created_by_import"]):
                raise LegacyObjectConflict("LEGACY_OBJECT_NOT_IMPORT_OWNED")
            if row.get("created_version_id"):
                raise LegacyObjectConflict("LEGACY_OBJECT_VERSION_ALREADY_OWNED")
            if row["status"] not in {"pending", "orphaned"}:
                raise LegacyObjectConflict("LEGACY_OBJECT_RECONCILE_STATE_INVALID")
            stored = self.store.get_version(item.object_key, version_id)
            if stored is None:
                raise LegacyObjectConflict("LEGACY_OBJECT_OWNED_VERSION_MISSING")
            _validate_payload(item, stored)
            self.ledger.set_created_version(item, version_id)
            self.ledger.set_status(item, "orphaned")
            counts["unchanged"] += 1
            return ObjectOperationResult("complete", counts)
        except LegacyObjectConflict as exc:
            counts["conflict"] += 1
            return ObjectOperationResult("failed", counts, (exc.code,))
        except Exception:
            counts["conflict"] += 1
            return ObjectOperationResult(
                "failed", counts, ("LEGACY_OBJECT_RECONCILE_FAILED",)
            )

    def orphan(
        self,
        items: list[PlannedLegacyObject],
        *,
        only_object_ids: set[str] | None = None,
    ) -> ObjectOperationResult:
        """Persist the retryable object-only state after a target DB failure."""
        counts = _counts(planned=len(items))
        blockers: list[str] = []
        for item in items:
            try:
                if only_object_ids is not None and item.object_id not in only_object_ids:
                    counts["unchanged"] += 1
                    continue
                row = self.ledger.get(item)
                if (
                    row is None
                    or item.payload is None
                    or row["status"] == "deleted"
                    or not bool(row["created_by_import"])
                ):
                    counts["unchanged"] += 1
                    continue
                _validate_row(item, row)
                self.ledger.set_status(item, "orphaned", "LEGACY_OBJECT_TARGET_APPLY_FAILED")
                counts["orphaned"] += 1
            except Exception:
                blockers.append("LEGACY_OBJECT_ORPHAN_STATE_FAILED")
                counts["conflict"] += 1
        blockers.append("LEGACY_OBJECT_TARGET_APPLY_FAILED")
        return ObjectOperationResult("partial", counts, tuple(blockers))

    def _mark_orphaned(self, item: PlannedLegacyObject, code: str) -> None:
        try:
            if self.ledger.get(item) is not None:
                self.ledger.set_status(item, "orphaned", code)
        except Exception:
            pass

    def _mark_batch_orphans(
        self, items: list[PlannedLegacyObject], staged_object_ids: set[str]
    ) -> int:
        orphaned = 0
        for item in items:
            try:
                if item.object_id not in staged_object_ids:
                    continue
                row = self.ledger.get(item)
                if (
                    row is None
                    or item.payload is None
                    or not bool(row["created_by_import"])
                    or row["status"] in {"deleted", "orphaned"}
                ):
                    continue
                self.ledger.set_status(item, "orphaned", "LEGACY_OBJECT_BATCH_APPLY_FAILED")
                orphaned += 1
            except Exception:
                continue
        return orphaned


class LegacyObjectConflict(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def plan_legacy_objects(
    source: LegacySource,
    *,
    import_id: str,
    tenant_id: str,
    project_id: str,
    source_project_id: str,
) -> list[PlannedLegacyObject]:
    items: list[PlannedLegacyObject] = []
    for row in source.rows("project_artifacts", source_project_id):
        artifact_key = str(row.get("artifact_key") or row.get("key") or "").strip()
        if not artifact_key:
            raise LegacyObjectConflict("LEGACY_ARTIFACT_KEY_MISSING")
        raw = row.get("payload_json")
        if not isinstance(raw, str):
            raise LegacyObjectConflict("LEGACY_ARTIFACT_PAYLOAD_INVALID")
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LegacyObjectConflict("LEGACY_ARTIFACT_PAYLOAD_INVALID") from exc
        items.append(
            _planned_object(
                payload=raw.encode("utf-8"),
                source_key=f"project_artifact:{artifact_key}",
                source_path=None,
                object_kind="project_artifact",
                media_type="application/json; charset=utf-8",
                source_table="project_artifacts",
                artifact_kind=artifact_key,
                import_id=import_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        )
    for row in source.rows("archive_sources", source_project_id):
        raw_path = str(row.get("file_path") or "").strip()
        path = _authorized_artifact_path(source.artifact_root, raw_path)
        payload = path.read_bytes() if path is not None else None
        media_type = _media_type(path) if path is not None else None
        items.append(
            _planned_object(
                payload=payload,
                source_key=f"archive_source:{_sha256(raw_path.encode('utf-8'))}",
                source_path=raw_path,
                object_kind="archive_source",
                media_type=media_type,
                source_table="archive_sources",
                artifact_kind="source_file",
                project_name=_optional_text(row.get("project_name")),
                source_mtime=_optional_datetime(row.get("file_mtime")),
                legacy_synced_at=_optional_datetime(row.get("synced_at")),
                source_basename=_safe_basename(raw_path),
                unsupported_reason=(
                    "APPROVED_LEGACY_SOURCE_PATH_UNSUPPORTED" if path is None else None
                ),
                import_id=import_id,
                tenant_id=tenant_id,
                project_id=project_id,
            )
        )
    return sorted(
        items, key=lambda item: (item.object_kind, item.source_key_hash, item.sha256 or "")
    )


def object_lifecycle_from_env(target_dsn: str) -> LegacyObjectLifecycle | None:
    values = {name: os.environ.get(name, "").strip() for name in OBJECT_ENV_NAMES}
    configured = [name for name, value in values.items() if value]
    if not configured:
        return None
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError("legacy object storage configuration is incomplete")
    use_ssl_value = os.environ.get("MIROFISH_OBJECT_STORAGE_USE_SSL", "true").strip().lower()
    if use_ssl_value not in {"true", "false"}:
        raise RuntimeError("MIROFISH_OBJECT_STORAGE_USE_SSL must be true or false")
    store = LegacyS3ObjectStore(
        endpoint=values["MIROFISH_OBJECT_STORAGE_ENDPOINT"],
        bucket=values["MIROFISH_OBJECT_STORAGE_BUCKET"],
        access_key=values["MIROFISH_OBJECT_STORAGE_ACCESS_KEY"],
        secret_key=values["MIROFISH_OBJECT_STORAGE_SECRET_KEY"],
        use_ssl=use_ssl_value == "true",
        region=os.environ.get("MIROFISH_OBJECT_STORAGE_REGION", "us-east-1"),
    )
    return LegacyObjectLifecycle(store, PostgresLegacyObjectLedger.from_dsn(target_dsn))


def _planned_object(
    *,
    payload: bytes | None,
    source_key: str,
    source_path: str | None,
    object_kind: str,
    media_type: str | None,
    source_table: str,
    artifact_kind: str,
    import_id: str,
    tenant_id: str,
    project_id: str,
    project_name: str | None = None,
    source_mtime: datetime | None = None,
    legacy_synced_at: datetime | None = None,
    source_basename: str | None = None,
    unsupported_reason: str | None = None,
) -> PlannedLegacyObject:
    source_key_hash = _sha256(source_key.encode("utf-8"))
    payload_hash = _sha256(payload) if payload is not None else None
    object_key = None
    if payload_hash is not None:
        object_key = (
            f"projects/{project_id}/legacy-imports/{import_id}/{object_kind}/"
            f"{source_key_hash}/{payload_hash}"
        )
    identity = f"{tenant_id}:{project_id}:{source_key_hash}:{payload_hash or 'metadata-only'}"
    object_id = str(uuid.uuid5(uuid.UUID(import_id), identity))
    return PlannedLegacyObject(
        object_id=object_id,
        tenant_id=tenant_id,
        project_id=project_id,
        import_id=import_id,
        object_kind=object_kind,
        source_table=source_table,
        artifact_kind=artifact_kind,
        source_key_hash=source_key_hash,
        project_name=project_name,
        source_mtime=source_mtime,
        legacy_synced_at=legacy_synced_at,
        source_basename=source_basename,
        path_hash=_sha256(source_path.encode("utf-8")) if source_path is not None else None,
        object_key=object_key,
        sha256=payload_hash,
        size_bytes=len(payload) if payload is not None else None,
        media_type=media_type,
        payload=payload,
        unsupported_reason=unsupported_reason,
    )


def _authorized_artifact_path(root: Path | None, raw_path: str) -> Path | None:
    if root is None or not raw_path:
        return None
    normalized = raw_path.replace("\\", "/")
    relative = Path(normalized)
    if relative.is_absolute() or PureWindowsPath(raw_path).is_absolute():
        return None
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _validate_row(item: PlannedLegacyObject, row: dict[str, Any]) -> None:
    expected = {
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
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise LegacyObjectConflict("LEGACY_OBJECT_LEDGER_CONFLICT")


def _validate_payload(item: PlannedLegacyObject, payload: bytes) -> None:
    if item.payload is None or item.size_bytes is None or item.sha256 is None:
        raise LegacyObjectConflict("LEGACY_OBJECT_PLAN_INVALID")
    if len(payload) != item.size_bytes or _sha256(payload) != item.sha256:
        raise LegacyObjectConflict("LEGACY_OBJECT_CONTENT_CONFLICT")


def _required_object_values(item: PlannedLegacyObject) -> tuple[str, bytes, str]:
    if item.object_key is None or item.payload is None or item.media_type is None:
        raise LegacyObjectConflict("LEGACY_OBJECT_PLAN_INVALID")
    return item.object_key, item.payload, item.media_type


def _unsupported_reasons(items: list[PlannedLegacyObject]) -> tuple[str, ...]:
    return tuple(sorted({item.unsupported_reason for item in items if item.unsupported_reason}))


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _optional_datetime(value: Any) -> datetime | None:
    normalized = _optional_text(value)
    if normalized is None:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        epoch_seconds = Decimal(normalized)
        if not epoch_seconds.is_finite():
            raise ValueError("non-finite Unix timestamp")
        return datetime.fromtimestamp(float(epoch_seconds), tz=timezone.utc)
    except (InvalidOperation, ValueError, OverflowError, OSError) as exc:
        raise LegacyObjectConflict("LEGACY_ARCHIVE_SOURCE_METADATA_INVALID") from exc


def _safe_basename(raw_path: str) -> str | None:
    if not raw_path:
        return None
    return _optional_text(Path(raw_path.replace("\\", "/")).name)


def _media_type(path: Path) -> str:
    if path.suffix.lower() in {".txt", ".md"}:
        return "text/plain; charset=utf-8"
    return "application/octet-stream"


def _counts(*, planned: int) -> dict[str, int]:
    return {
        "planned": planned,
        "imported": 0,
        "unchanged": 0,
        "conflict": 0,
        "rolled_back": 0,
        "orphaned": 0,
        "metadata_only": 0,
    }


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _aws_signing_key(secret_key: str, date_stamp: str, region: str) -> bytes:
    date_key = hmac.new(
        f"AWS4{secret_key}".encode("utf-8"),
        date_stamp.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    region_key = hmac.new(date_key, region.encode("utf-8"), hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()
