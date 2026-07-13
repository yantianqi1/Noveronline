from __future__ import annotations

import json
import time
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Any, Callable

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import ImportPlan, PlannedRecord, make_report, stable_hash


class TargetConflict(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class PostgresImportTarget:
    def __init__(self, connect: Callable[[], Any], heartbeat: Callable[[str], None] | None = None) -> None:
        self.connect = connect
        self.heartbeat = heartbeat or (lambda _detail: None)

    @classmethod
    def from_dsn(
        cls, dsn: str, heartbeat: Callable[[str], None] | None = None
    ) -> "PostgresImportTarget":
        import psycopg

        return cls(lambda: psycopg.connect(dsn, row_factory=dict_row), heartbeat)

    def apply(self, plan: ImportPlan) -> dict[str, Any]:
        started = time.monotonic()
        counts = self._base_counts(plan)
        if "SOURCE_PROJECT_METADATA_ABSENT" in plan.families["project"].reason_codes:
            return self._report(
                plan,
                "apply",
                "failed",
                counts,
                ["SOURCE_PROJECT_METADATA_ABSENT"],
                started,
            )
        current_family = "project"
        try:
            with self.connect() as connection:
                with connection.transaction():
                    self._set_context(connection, plan)
                    self._validate_scope(connection, plan)
                    ledger = self._ledger(connection, plan.import_id)
                    self._validate_ledger(plan, ledger)
                    if ledger is None:
                        self._validate_empty_graph_target(connection, plan)
                    inserted_any = False
                    for record in plan.records:
                        current_family = record.family
                        self.heartbeat(f"apply:{record.family}")
                        inserted = self._insert_or_compare(connection, record)
                        counts[record.family]["imported" if inserted else "unchanged"] += 1
                        inserted_any = inserted_any or inserted
                    if inserted_any or ledger is None:
                        self._write_audit(
                            connection,
                            plan,
                            "legacy_import.apply",
                            "applied",
                            counts,
                            checkpoint="transaction_committed",
                        )
        except TargetConflict as exc:
            counts[current_family]["conflict"] += 1
            return self._report(plan, "apply", "failed", counts, [exc.code], started)
        except Exception:
            counts[current_family]["conflict"] += 1
            return self._report(plan, "apply", "failed", counts, ["TARGET_TRANSACTION_FAILED"], started)
        status = "partial" if self._has_deferred(counts) else "complete"
        return self._report(plan, "apply", status, counts, [], started)

    def preflight(self, plan: ImportPlan) -> str | None:
        """Validate immutable import identity and target scope before object writes."""
        try:
            with self.connect() as connection:
                with connection.transaction():
                    self._set_context(connection, plan)
                    self._validate_scope(connection, plan)
                    ledger = self._ledger(connection, plan.import_id)
                    self._validate_ledger(plan, ledger)
                    if ledger is None:
                        self._validate_empty_graph_target(connection, plan)
        except TargetConflict as exc:
            return exc.code
        except Exception:
            return "TARGET_PREFLIGHT_FAILED"
        return None

    def verify(self, plan: ImportPlan) -> dict[str, Any]:
        started = time.monotonic()
        counts = self._base_counts(plan)
        blockers: list[str] = []
        try:
            with self.connect() as connection:
                with connection.transaction():
                    self._set_context(connection, plan)
                    self._validate_scope(connection, plan)
                    ledger = self._ledger(connection, plan.import_id)
                    self._validate_ledger(plan, ledger)
                    if ledger is None:
                        blockers.append("IMPORT_LEDGER_MISSING")
                    for record in plan.records:
                        actual = self._fetch_record(connection, record)
                        if actual is None:
                            counts[record.family]["conflict"] += 1
                            blockers.append("TARGET_ROW_MISSING")
                        elif self._record_hash(record, actual) != record.row_hash:
                            counts[record.family]["conflict"] += 1
                            blockers.append("TARGET_ROW_CHANGED")
                        else:
                            counts[record.family]["unchanged"] += 1
                    if not self._cross_tenant_hidden(connection, plan):
                        blockers.append("RLS_CROSS_TENANT_VISIBLE")
        except TargetConflict as exc:
            blockers.append(exc.code)
        except Exception:
            blockers.append("TARGET_VERIFY_FAILED")
        status = "failed" if blockers else ("partial" if self._has_deferred(counts) else "complete")
        return self._report(plan, "verify", status, counts, blockers, started)

    def rollback(self, plan: ImportPlan) -> dict[str, Any]:
        started = time.monotonic()
        counts = self._base_counts(plan)
        blockers: list[str] = []
        try:
            with self.connect() as connection:
                with connection.transaction():
                    self._set_context(connection, plan)
                    ledger = self._ledger(connection, plan.import_id)
                    self._validate_ledger(plan, ledger)
                    if ledger is None:
                        raise TargetConflict("IMPORT_LEDGER_MISSING")
                    applied_at = ledger["created_at"]
                    blockers.extend(self._rollback_preflight(connection, plan, applied_at))
                    blockers.extend(self._external_reference_blockers(connection, plan))
                    if blockers:
                        raise TargetConflict("ROLLBACK_GUARD_BLOCKED")
                    for record in reversed(plan.records):
                        deleted = self._delete_record(connection, plan, record)
                        counts[record.family]["rolled_back"] += deleted
                    self._write_audit(
                        connection,
                        plan,
                        "legacy_import.rollback",
                        "rolled_back",
                        counts,
                        checkpoint="rollback_committed",
                    )
        except TargetConflict as exc:
            blockers.append(exc.code)
            return self._report(plan, "rollback", "failed", counts, blockers, started)
        except Exception:
            blockers.append("TARGET_ROLLBACK_FAILED")
            return self._report(plan, "rollback", "failed", counts, blockers, started)
        return self._report(plan, "rollback", "complete", counts, [], started)

    @staticmethod
    def _validate_empty_graph_target(connection: Any, plan: ImportPlan) -> None:
        planned_graph_ids = [
            record.key for record in plan.records if record.table == "story_graph_snapshots"
        ]
        if not planned_graph_ids:
            return
        existing = connection.execute(
            """
            SELECT 1
            FROM story_graph_snapshots
            WHERE tenant_id = %s::uuid
              AND project_id = %s::uuid
              AND NOT (graph_id = ANY(%s::uuid[]))
            LIMIT 1
            """,
            (plan.tenant_id, plan.project_id, planned_graph_ids),
        ).fetchone()
        if existing is not None:
            raise TargetConflict("TARGET_GRAPH_ALREADY_EXISTS")

    def _insert_or_compare(self, connection: Any, record: PlannedRecord) -> bool:
        columns = list(record.values)
        values = [self._adapt(record.values[column]) for column in columns]
        query = sql.SQL("INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
                        "ON CONFLICT ({key}) DO NOTHING RETURNING {key}").format(
            table=sql.Identifier(record.table),
            columns=sql.SQL(", ").join(map(sql.Identifier, columns)),
            placeholders=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            key=sql.Identifier(record.key_column),
        )
        inserted = connection.execute(query, values).fetchone()
        if inserted is not None:
            return True
        actual = self._fetch_record(connection, record)
        if actual is None or self._record_hash(record, actual) != record.row_hash:
            raise TargetConflict("TARGET_ROW_CONFLICT")
        return False

    def _fetch_record(self, connection: Any, record: PlannedRecord) -> dict[str, Any] | None:
        query = sql.SQL("SELECT {columns} FROM {table} WHERE {key} = %s::uuid").format(
            columns=sql.SQL(", ").join(map(sql.Identifier, record.compare_columns)),
            table=sql.Identifier(record.table),
            key=sql.Identifier(record.key_column),
        )
        return connection.execute(query, (record.key,)).fetchone()

    def _delete_record(self, connection: Any, plan: ImportPlan, record: PlannedRecord) -> int:
        query = sql.SQL(
            "DELETE FROM {table} WHERE {key} = %s::uuid AND tenant_id = %s::uuid"
        ).format(table=sql.Identifier(record.table), key=sql.Identifier(record.key_column))
        cursor = connection.execute(query, (record.key, plan.tenant_id))
        return max(0, cursor.rowcount)

    def _rollback_preflight(self, connection: Any, plan: ImportPlan, applied_at: datetime) -> list[str]:
        blockers: list[str] = []
        for record in plan.records:
            actual = self._fetch_record(connection, record)
            if actual is None:
                continue
            if self._record_hash(record, actual) != record.row_hash:
                blockers.append("IMPORTED_ROW_MODIFIED")
                continue
            has_updated_at = connection.execute(
                """
                SELECT 1
                FROM pg_attribute
                WHERE attrelid = %s::regclass AND attname = 'updated_at' AND NOT attisdropped
                """,
                (record.table,),
            ).fetchone()
            if has_updated_at is None:
                continue
            updated = connection.execute(
                sql.SQL("SELECT updated_at FROM {table} WHERE {key} = %s::uuid").format(
                    table=sql.Identifier(record.table), key=sql.Identifier(record.key_column)
                ),
                (record.key,),
            ).fetchone()
            if updated and updated["updated_at"] > applied_at:
                blockers.append("IMPORTED_ROW_MODIFIED")
        return blockers

    def _external_reference_blockers(self, connection: Any, plan: ImportPlan) -> list[str]:
        owned: dict[str, set[str]] = defaultdict(set)
        key_columns: dict[str, str] = {}
        records_by_table: dict[str, list[PlannedRecord]] = defaultdict(list)
        for record in plan.records:
            owned[record.table].add(record.key)
            key_columns[record.table] = record.key_column
            records_by_table[record.table].append(record)
        blockers: list[str] = []
        references = connection.execute(
            """
            SELECT child.relname AS child_table,
                   parent.relname AS parent_table,
                   array_agg(child_col.attname ORDER BY keys.ordinality) AS child_fks,
                   array_agg(parent_col.attname ORDER BY keys.ordinality) AS parent_keys
            FROM pg_constraint fk
            JOIN pg_class child ON child.oid = fk.conrelid
            JOIN pg_class parent ON parent.oid = fk.confrelid
            JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
            JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
            CROSS JOIN LATERAL unnest(fk.conkey, fk.confkey)
                WITH ORDINALITY AS keys(child_attnum, parent_attnum, ordinality)
            JOIN pg_attribute child_col
              ON child_col.attrelid = child.oid AND child_col.attnum = keys.child_attnum
            JOIN pg_attribute parent_col
              ON parent_col.attrelid = parent.oid AND parent_col.attnum = keys.parent_attnum
            WHERE fk.contype = 'f'
              AND child_ns.nspname = current_schema()
              AND parent_ns.nspname = current_schema()
            GROUP BY fk.oid, child.relname, parent.relname
            """
        ).fetchall()
        for reference in references:
            parent_records = records_by_table.get(reference["parent_table"], [])
            if not parent_records:
                continue
            child_table = reference["child_table"]
            child_key = key_columns.get(child_table)
            child_ids = sorted(owned.get(child_table, set()))
            for parent_record in parent_records:
                parent_values = [parent_record.values.get(name) for name in reference["parent_keys"]]
                if any(value is None for value in parent_values):
                    continue
                predicates = [
                    sql.SQL("{column} = %s").format(column=sql.Identifier(column))
                    for column in reference["child_fks"]
                ]
                parameters: list[Any] = list(parent_values)
                if child_key and child_ids:
                    predicates.append(
                        sql.SQL("NOT ({column} = ANY(%s::uuid[]))").format(
                            column=sql.Identifier(child_key)
                        )
                    )
                    parameters.append(child_ids)
                query = sql.SQL("SELECT 1 FROM {table} WHERE {where} LIMIT 1").format(
                    table=sql.Identifier(child_table),
                    where=sql.SQL(" AND ").join(predicates),
                )
                if connection.execute(query, parameters).fetchone() is not None:
                    blockers.append("IMPORTED_ROW_REFERENCED")
                    break
        blockers.extend(self._soft_reference_blockers(connection, owned))
        return blockers

    @staticmethod
    def _soft_reference_blockers(connection: Any, owned: dict[str, set[str]]) -> list[str]:
        references = (
            ("entities", "entity_id", "story_graph_nodes", "canonical_entity_id", "node_id"),
            ("assets", "asset_id", "worldline_prepared_agents", "source_asset_id", "agent_id"),
            ("worldline_sessions", "session_id", "worldline_saved_paths", "session_id", "path_id"),
            ("story_graph_nodes", "node_id", "story_graph_evidence", "owner_id", "evidence_id"),
            ("story_graph_edges", "edge_id", "story_graph_evidence", "owner_id", "evidence_id"),
        )
        blockers: list[str] = []
        for parent_table, _parent_key, child_table, child_fk, child_key in references:
            parent_ids = sorted(owned.get(parent_table, set()))
            if not parent_ids:
                continue
            query = sql.SQL("SELECT {key}::text AS child_id FROM {table} WHERE {fk} = ANY(%s::uuid[])").format(
                key=sql.Identifier(child_key), table=sql.Identifier(child_table), fk=sql.Identifier(child_fk)
            )
            child_ids = {row["child_id"] for row in connection.execute(query, (parent_ids,)).fetchall()}
            if child_ids - owned.get(child_table, set()):
                blockers.append("IMPORTED_ROW_REFERENCED")
        return blockers

    def _cross_tenant_hidden(self, connection: Any, plan: ImportPlan) -> bool:
        other_tenant = str(uuid.uuid5(uuid.UUID(plan.tenant_id), "legacy-import-rls-probe"))
        connection.execute(
            "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
            (other_tenant, plan.actor_user_id),
        )
        for record in plan.records:
            query = sql.SQL("SELECT 1 FROM {table} WHERE {key} = %s::uuid").format(
                table=sql.Identifier(record.table), key=sql.Identifier(record.key_column)
            )
            if connection.execute(query, (record.key,)).fetchone() is not None:
                return False
        return True

    @staticmethod
    def _set_context(connection: Any, plan: ImportPlan) -> None:
        connection.execute(
            "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
            (plan.tenant_id, plan.actor_user_id),
        )

    @staticmethod
    def _validate_scope(connection: Any, plan: ImportPlan) -> None:
        project = connection.execute(
            "SELECT 1 FROM projects WHERE tenant_id = %s::uuid AND project_id = %s::uuid",
            (plan.tenant_id, plan.project_id),
        ).fetchone()
        actor = connection.execute(
            "SELECT 1 FROM users WHERE user_id = %s::uuid",
            (plan.actor_user_id,),
        ).fetchone()
        if project is None:
            raise TargetConflict("TARGET_PROJECT_NOT_FOUND")
        if actor is None:
            raise TargetConflict("TARGET_ACTOR_NOT_FOUND")

    @staticmethod
    def _ledger(connection: Any, import_id: str) -> dict[str, Any] | None:
        return connection.execute(
            """
            SELECT metadata_jsonb, created_at
            FROM audit_logs
            WHERE resource_type = 'legacy_import'
              AND resource_id = %s::uuid
              AND action = 'legacy_import.apply'
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (import_id,),
        ).fetchone()

    @staticmethod
    def _validate_ledger(plan: ImportPlan, ledger: dict[str, Any] | None) -> None:
        if ledger is None:
            return
        metadata = ledger["metadata_jsonb"]
        if metadata.get("source_fingerprint") != plan.source.fingerprint:
            raise TargetConflict("IMPORT_ID_SOURCE_FINGERPRINT_MISMATCH")
        if metadata.get("plan_hash") != plan.plan_hash:
            raise TargetConflict("IMPORT_ID_PLAN_MISMATCH")

    @staticmethod
    def _write_audit(
        connection: Any,
        plan: ImportPlan,
        action: str,
        status: str,
        counts: dict[str, dict[str, int]],
        *,
        checkpoint: str,
    ) -> None:
        metadata = {
            "status": status,
            "source_fingerprint": plan.source.fingerprint,
            "plan_hash": plan.plan_hash,
            "family_counts": counts,
            "checkpoint": checkpoint,
        }
        connection.execute(
            """
            INSERT INTO audit_logs (
                tenant_id, audit_id, actor_user_id, action, resource_type,
                resource_id, project_id, request_id, metadata_jsonb
            ) VALUES (%s::uuid, %s::uuid, %s::uuid, %s, 'legacy_import', %s::uuid, %s::uuid, %s, %s::jsonb)
            """,
            (
                plan.tenant_id,
                str(uuid.uuid4()),
                plan.actor_user_id,
                action,
                plan.import_id,
                plan.project_id,
                plan.import_id,
                json.dumps(metadata, sort_keys=True),
            ),
        )

    @staticmethod
    def _record_hash(record: PlannedRecord, actual: dict[str, Any]) -> str:
        return stable_hash({name: _normalize(actual.get(name)) for name in record.compare_columns})

    @staticmethod
    def _adapt(value: Any) -> Any:
        if isinstance(value, (dict, list)):
            return Jsonb(value)
        return value

    @staticmethod
    def _base_counts(plan: ImportPlan) -> dict[str, dict[str, int]]:
        counts = {
            family: {
                "planned": len(item.records),
                "imported": 0,
                "unchanged": 0,
                "deferred": item.deferred_count,
                "unsupported": item.unsupported_count,
                "conflict": 0,
                "rolled_back": 0,
            }
            for family, item in plan.families.items()
        }
        counts["project"]["unchanged"] = plan.families["project"].source_count
        return counts

    @staticmethod
    def _has_deferred(counts: dict[str, dict[str, int]]) -> bool:
        return any(item["deferred"] or item["unsupported"] for item in counts.values())

    @staticmethod
    def _report(
        plan: ImportPlan,
        operation: str,
        status: str,
        counts: dict[str, dict[str, int]],
        blockers: list[str],
        started: float,
    ) -> dict[str, Any]:
        if operation in {"apply", "verify"}:
            blockers = blockers + [
                reason for family in plan.families.values() for reason in family.reason_codes
            ]
        return make_report(
            operation=operation,
            import_id=plan.import_id,
            status=status,  # type: ignore[arg-type]
            source_fingerprint=plan.source.fingerprint,
            plan_hash=plan.plan_hash,
            family_counts=counts,
            family_reasons={
                name: sorted(set(family.reason_codes))
                for name, family in plan.families.items()
                if family.reason_codes
            },
            blockers=blockers,
            duration_ms=int((time.monotonic() - started) * 1000),
        )


def _normalize(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value
