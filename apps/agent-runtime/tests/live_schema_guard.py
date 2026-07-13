import re
from pathlib import Path
from typing import Iterable, Protocol


BASELINE_VERSION = "0001_core_saas"
DISPOSABLE_DATABASE_NAME = re.compile(r"^mirofish_test_[a-z0-9_]+$")


class Cursor(Protocol):
    def execute(self, query: str, params: object = None) -> object: ...
    def fetchone(self) -> tuple[object, ...]: ...


def ensure_live_schema(cursor: Cursor, migration_path: Path, required_tables: Iterable[str]) -> str:
    require_disposable_live_database(cursor)
    cursor.execute("SELECT to_regclass('public.mirofish_schema_migrations') IS NOT NULL")
    ledger_exists = bool(cursor.fetchone()[0])
    if ledger_exists:
        cursor.execute(
            "SELECT EXISTS (SELECT 1 FROM mirofish_schema_migrations WHERE version = %s)",
            (BASELINE_VERSION,),
        )
        if not bool(cursor.fetchone()[0]):
            raise RuntimeError(f"schema migration ledger is present without {BASELINE_VERSION}")
        _validate_required_tables(cursor, required_tables)
        return "ledger"

    cursor.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
    )
    table_count = int(cursor.fetchone()[0])
    if table_count:
        raise RuntimeError(
            "refusing raw baseline without migration ledger: "
            f"public schema already has {table_count} base tables"
        )
    cursor.execute(migration_path.read_text(encoding="utf-8"))
    _validate_required_tables(cursor, required_tables)
    return "fresh"


def require_disposable_live_database(cursor: Cursor) -> None:
    cursor.execute(
        "SELECT current_database(), COALESCE(current_setting('mirofish.live_test', true), '')"
    )
    database_name, marker = cursor.fetchone()
    normalized_name = str(database_name).strip().lower()
    if not DISPOSABLE_DATABASE_NAME.fullmatch(normalized_name) or str(marker).strip() != "on":
        raise RuntimeError(
            f"refusing live test database {normalized_name!r} without disposable database name and marker"
        )


def _validate_required_tables(cursor: Cursor, required_tables: Iterable[str]) -> None:
    for table in required_tables:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (f"public.{table}",))
        if not bool(cursor.fetchone()[0]):
            raise RuntimeError(f"required live-test table {table} is missing")
