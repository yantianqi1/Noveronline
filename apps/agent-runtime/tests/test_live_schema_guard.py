import os
from pathlib import Path

import psycopg
import pytest

from live_schema_guard import ensure_live_schema


def test_upgraded_ledger_skips_raw_baseline_and_preserves_recovery_grants() -> None:
    cursor = RecordingCursor(
        ledger=True,
        versions={"0001_core_saas", "0010_auth_recovery_privilege_convergence"},
        tables={"password_reset_tokens", "password_reset_delivery_outbox"},
    )

    mode = ensure_live_schema(
        cursor,
        Path("/must/not/be/read.sql"),
        ("password_reset_tokens", "password_reset_delivery_outbox"),
    )

    assert mode == "ledger"
    assert cursor.raw_sql == []


def test_existing_public_schema_without_ledger_fails_closed() -> None:
    cursor = RecordingCursor(public_table_count=1)
    with pytest.raises(RuntimeError, match="refusing raw baseline"):
        ensure_live_schema(cursor, Path("/must/not/be/read.sql"), ())
    assert cursor.raw_sql == []


def test_runtime_database_or_missing_marker_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="refusing live test database"):
        ensure_live_schema(RecordingCursor(database_name="mirofish"), Path("/unused.sql"), ())
    with pytest.raises(RuntimeError, match="refusing live test database"):
        ensure_live_schema(
            RecordingCursor(database_name="mirofish_test_unit", live_test_marker=""),
            Path("/unused.sql"),
            (),
        )


def test_upgraded_live_database_guard_preserves_recovery_table_direct_grants() -> None:
    database_url = os.environ.get("MIROFISH_SCHEMA_GUARD_LIVE_DATABASE_URL", "").strip()
    if not database_url:
        pytest.skip("set MIROFISH_SCHEMA_GUARD_LIVE_DATABASE_URL to verify upgraded DB ACL preservation")
    with psycopg.connect(database_url) as connection:
        with connection.cursor() as cursor:
            before = _recovery_table_acls(cursor)
            assert ensure_live_schema(
                cursor,
                Path("/raw-baseline-must-not-be-read.sql"),
                ("password_reset_tokens", "password_reset_delivery_outbox"),
            ) == "ledger"
            after = _recovery_table_acls(cursor)
    assert before == after


def _recovery_table_acls(cursor: object) -> list[tuple[str, str]]:
    cursor.execute(
        "SELECT relname, COALESCE(relacl::text, '') FROM pg_class "
        "WHERE oid IN ('public.password_reset_tokens'::regclass, 'public.password_reset_delivery_outbox'::regclass) "
        "ORDER BY relname"
    )
    return cursor.fetchall()


class RecordingCursor:
    def __init__(
        self,
        *,
        ledger: bool = False,
        versions: set[str] | None = None,
        tables: set[str] | None = None,
        public_table_count: int = 0,
        database_name: str = "mirofish_test_unit",
        live_test_marker: str = "on",
    ) -> None:
        self.ledger = ledger
        self.versions = versions or set()
        self.tables = tables or set()
        self.public_table_count = public_table_count
        self.database_name = database_name
        self.live_test_marker = live_test_marker
        self.result: tuple[object, ...] = (False,)
        self.raw_sql: list[str] = []

    def execute(self, query: str, params: object = None) -> None:
        normalized = " ".join(query.split()).lower()
        if normalized.startswith("select current_database()"):
            self.result = (self.database_name, self.live_test_marker)
        elif "to_regclass('public.mirofish_schema_migrations')" in normalized:
            self.result = (self.ledger,)
        elif "from mirofish_schema_migrations" in normalized:
            version = params[0] if isinstance(params, tuple) else ""
            self.result = (version in self.versions,)
        elif "from information_schema.tables" in normalized:
            self.result = (self.public_table_count,)
        elif normalized.startswith("select to_regclass(%s)"):
            table = params[0].removeprefix("public.") if isinstance(params, tuple) else ""
            self.result = (table in self.tables,)
        else:
            self.raw_sql.append(query)

    def fetchone(self) -> tuple[object, ...]:
        return self.result
