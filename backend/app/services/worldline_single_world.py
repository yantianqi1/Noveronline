"""单世界世界线约束与辅助函数。"""

from __future__ import annotations

from typing import Iterable, Optional


MAIN_WORLD_BRANCH_ID = "main"
MAIN_WORLD_TITLE = "当前世界"
LEGACY_MULTI_BRANCH_ERROR = "旧版多分支会话暂不支持，请重新创建单世界世界线会话"
UNSUPPORTED_BRANCH_ERROR = "当前版本仅支持主世界 branch_id=main"


def ensure_single_world_session(session) -> bool:
    branches = list(session.branches or [])
    if len(branches) != 1:
        raise ValueError(LEGACY_MULTI_BRANCH_ERROR)
    branch = branches[0]
    changed = False
    if session.branch_count != 1:
        session.branch_count = 1
        changed = True
    if branch.branch_id != MAIN_WORLD_BRANCH_ID:
        branch.branch_id = MAIN_WORLD_BRANCH_ID
        changed = True
    if not str(branch.title or "").strip():
        branch.title = MAIN_WORLD_TITLE
        changed = True
    return changed


def current_world(session):
    ensure_single_world_session(session)
    return session.branches[0]


def resolve_branch_id(branch_id: Optional[str]) -> str:
    value = str(branch_id or "").strip()
    if not value:
        return MAIN_WORLD_BRANCH_ID
    if value != MAIN_WORLD_BRANCH_ID:
        raise ValueError(UNSUPPORTED_BRANCH_ERROR)
    return MAIN_WORLD_BRANCH_ID


def resolve_branch_ids(branch_ids: Optional[Iterable[str]]) -> list[str]:
    if not branch_ids:
        return [MAIN_WORLD_BRANCH_ID]
    values = [str(item).strip() for item in branch_ids if str(item).strip()]
    if not values:
        return [MAIN_WORLD_BRANCH_ID]
    invalid = [item for item in values if item != MAIN_WORLD_BRANCH_ID]
    if invalid:
        raise ValueError(UNSUPPORTED_BRANCH_ERROR)
    return [MAIN_WORLD_BRANCH_ID]
