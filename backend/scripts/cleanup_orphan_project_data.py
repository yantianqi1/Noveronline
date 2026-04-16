"""清理「已删除项目」的数据库孤儿数据。

背景
----

2026-04-16 之前的 DELETE /api/project/{pid} 只做了 ``shutil.rmtree`` 清文件系统，
数据库里所有以 ``project_id`` 标注的行都留成了孤儿。修复后新删除会走级联清理
(`cascade_delete_project`)，但此前已被删除的项目的数据库行仍然残留。

本脚本一次性扫描：
- 文件系统上 ``backend/uploads/projects/`` 下还存在的目录
- 数据库里出现过的所有 project_id
两者的差集即为「已被删除但数据残留」的孤儿项目。

用法
----

dry-run 只报告不删除（默认）::

    cd backend
    PYTHONPATH=$(pwd) uv run python scripts/cleanup_orphan_project_data.py

真正执行清理::

    PYTHONPATH=$(pwd) uv run python scripts/cleanup_orphan_project_data.py --execute

也可以只清理指定 project_id::

    PYTHONPATH=$(pwd) uv run python scripts/cleanup_orphan_project_data.py --execute --only proj_abc123
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# 加入 backend 到 sys.path，允许脚本以绝对导入运行。
_HERE = Path(__file__).resolve().parent
_BACKEND_ROOT = _HERE.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import func, select

from app.database import get_engine
from app.models.project import ProjectManager
from app.services.project_deletion_service import (
    ALL_PROJECT_SCOPED_TABLES,
    COVERED_BY_REPO_METHODS,
    cascade_delete_project,
)


def _list_filesystem_project_ids() -> set[str]:
    """扫 backend/uploads/projects/ 下现存目录名。"""
    base = Path(ProjectManager.PROJECTS_DIR)
    if not base.exists():
        return set()
    return {
        entry.name for entry in base.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    }


def _list_db_project_ids() -> set[str]:
    """扫所有项目范围表，收集出现过的 project_id。"""
    engine = get_engine()
    pids: set[str] = set()
    tables = list(ALL_PROJECT_SCOPED_TABLES) + list(COVERED_BY_REPO_METHODS)
    with engine.connect() as conn:
        for table in tables:
            if "project_id" not in table.c:
                continue
            rows = conn.execute(
                select(table.c.project_id)
                .where(table.c.project_id.is_not(None))
                .distinct()
            ).fetchall()
            for (pid,) in rows:
                if pid:
                    pids.add(pid)
    return pids


def _count_orphan_rows(pid: str) -> dict[str, int]:
    """只读统计给定 pid 在每张表里有多少行。"""
    engine = get_engine()
    counts: dict[str, int] = {}
    tables = list(ALL_PROJECT_SCOPED_TABLES) + list(COVERED_BY_REPO_METHODS)
    with engine.connect() as conn:
        for table in tables:
            if "project_id" not in table.c:
                continue
            n = conn.execute(
                select(func.count()).select_from(table).where(
                    table.c.project_id == pid,
                )
            ).scalar_one()
            if n:
                counts[table.name] = int(n)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true",
        help="真正执行删除；不加此开关时只做 dry-run 报告。",
    )
    parser.add_argument(
        "--only", metavar="PID", action="append", default=[],
        help="只处理指定 project_id，可多次传入。不加此开关则扫描所有孤儿。",
    )
    args = parser.parse_args()

    fs_pids = _list_filesystem_project_ids()
    db_pids = _list_db_project_ids()
    orphans = sorted(db_pids - fs_pids)

    if args.only:
        allowed = set(args.only)
        orphans = [p for p in orphans if p in allowed]
        missing = allowed - set(orphans)
        if missing:
            print(f"[warn] 以下 project_id 在 DB 里没有孤儿数据（跳过）: {sorted(missing)}")

    print(f"文件系统上的项目目录数量: {len(fs_pids)}")
    print(f"数据库里出现过的 project_id 数量: {len(db_pids)}")
    print(f"确认为孤儿的 project_id 数量: {len(orphans)}")
    print()

    if not orphans:
        print("没有孤儿数据，无需清理。")
        return 0

    total_rows = 0
    per_table_rows: dict[str, int] = {}
    for pid in orphans:
        counts = _count_orphan_rows(pid)
        if not counts:
            continue
        pid_total = sum(counts.values())
        total_rows += pid_total
        print(f"  {pid}  —  {pid_total} 行：")
        for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            per_table_rows[name] = per_table_rows.get(name, 0) + n
            print(f"      {name:<40} {n}")

    print()
    print(f"合计孤儿行数: {total_rows}")
    print(f"涉及表数量: {len(per_table_rows)}")
    print()

    if not args.execute:
        print("[dry-run] 未执行删除。加 --execute 开关才真正清理。")
        return 0

    print("[execute] 开始级联清理…")
    cleaned: dict[str, int] = {}
    for pid in orphans:
        stats = cascade_delete_project(pid)
        deleted_total = sum(v for v in stats.values() if isinstance(v, int))
        cleaned[pid] = deleted_total
        print(f"  ✓ {pid}  —  删除 {deleted_total} 行")

    print()
    print(f"完成。共处理 {len(cleaned)} 个孤儿项目。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
