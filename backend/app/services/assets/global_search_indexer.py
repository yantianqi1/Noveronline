"""全局 FTS 搜索索引。

把所有 silo 的可搜索条目镜像到统一数据库的 ``global_index`` 表中，
通过 ``SearchRepository`` 进行 CRUD 与搜索。

设计原则：
- **镜像，不写源** -- 索引出问题时只重建索引即可，不会破坏任何 silo。
- **以 UnifiedAssetView 为单一数据接入** -- 任何 source 修改 reader 后，
  ``reindex_project`` 立刻能跟上。
- **失败显式** -- 不静默吞错，按 CLAUDE.md 让异常向上抛。
"""

from __future__ import annotations

from typing import Any, Iterable

from ...database import get_engine
from ...repositories.search_repo import SearchRepository
from .unified_asset_view import ALL_SOURCES, UnifiedAssetView


MIN_QUERY_CHARS = 2


class QueryTooShort(ValueError):
    """Raised when a search query is shorter than the public contract."""


class GlobalSearchIndexer:
    """全局 FTS 索引。"""

    def __init__(self, repo: SearchRepository | None = None) -> None:
        self._repo = repo or SearchRepository(get_engine())

    # -- write ---------------------------------------------------------
    def upsert(self, items: Iterable[dict[str, Any]]) -> int:
        """批量写入 unified asset DTO。``items`` 元素必须含 source/source_ref。"""
        return self._repo.upsert(items)

    def delete(self, source: str, source_ref: str) -> bool:
        return self._repo.delete(source, source_ref)

    def delete_project(self, project_id: str, source: str | None = None) -> int:
        return self._repo.delete_project(project_id, source)

    def reindex_project(self, project_id: str) -> int:
        """对单个项目全量重建索引。"""
        view = UnifiedAssetView()
        result = view.list(project_id=project_id, page=1, page_size=10000)
        items = result["items"]
        # 清掉旧条目（仅这个 project 的所有 silo + 全局 assets 中归属此 project 的）
        self.delete_project(project_id)
        # 全局 assets 不一定带 project_id，需单独清并按 source 重写
        self._repo.delete_project(project_id, source="assets")
        return self.upsert(items)

    # -- read ----------------------------------------------------------
    def search(
        self,
        query: str,
        *,
        project_id: str | None = None,
        sources: Iterable[str] | None = None,
        entity_types: Iterable[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._repo.search(
            query,
            project_id=project_id,
            sources=sources,
            entity_types=entity_types,
            limit=limit,
            offset=offset,
        )
