from __future__ import annotations

import json
from typing import Any

import pytest

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import LLMFacilityError, ModuleBindingResolution
from mirofish_agents.temporal.assets import (
    ASSET_REINDEX_MODULE_KEY,
    OpenAICompatibleEmbeddingClient,
    PostgresAssetReindexer,
)


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-reindex-1",
        workflow_type="asset_reindex",
        actor_user_id="user-1",
        module_key=ASSET_REINDEX_MODULE_KEY,
        trace_id="trace-reindex-1",
        permissions={ASSET_REINDEX_MODULE_KEY: ["run"]},
    )


def _resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key=ASSET_REINDEX_MODULE_KEY,
        channel_id="channel-1",
        model_id="embedding-model-1",
        provider="openai-compatible",
        base_url="https://provider.example/v1",
        credential_ref="channel-1",
        supports_json=False,
        settings={"embedding_dimensions": 3},
    )


class StaticBindingResolver:
    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        assert context == _context()
        assert module_key == ASSET_REINDEX_MODULE_KEY
        return _resolution()


class StaticCredentialProvider:
    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        assert context == _context()
        assert credential_ref == "channel-1"
        return "provider-key"


class RecordingEmbeddingClient:
    def __init__(self, embeddings: list[list[float]]) -> None:
        self.embeddings = embeddings
        self.calls: list[dict[str, Any]] = []

    def embed_texts(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        texts: list[str],
    ) -> list[list[float]]:
        self.calls.append(
            {
                "context": context,
                "resolution": resolution,
                "api_key": api_key,
                "texts": texts,
            }
        )
        return self.embeddings


class ReindexCursor:
    def __init__(self, *, asset_rows: list[tuple[Any, ...]] | None = None, source_changed: bool = False) -> None:
        self.asset_rows = asset_rows or []
        self.source_changed = source_changed
        self.executed: list[tuple[str, tuple[Any, ...] | None]] = []
        self._last_query = ""

    def __enter__(self) -> "ReindexCursor":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None

    def execute(self, query: str, params: tuple[Any, ...] | None = None) -> None:
        self._last_query = query
        self.executed.append((query, params))

    def fetchall(self) -> list[tuple[Any, ...]]:
        return self.asset_rows

    def fetchone(self) -> Any:
        if "SELECT\n                         (SELECT count(*)" in self._last_query:
            count = len(self.asset_rows) if self.asset_rows else 1
            return (count, count, 0)
        if "RETURNING embedding_id" in self._last_query:
            return None if self.source_changed else ("embedding-1",)
        return None


class ReindexConnection:
    def __init__(self, cursor: ReindexCursor) -> None:
        self.cursor_instance = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self) -> ReindexCursor:
        return self.cursor_instance

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


def test_openai_compatible_embedding_client_calls_embeddings_endpoint_without_truncation() -> None:
    captured: dict[str, Any] = {}

    def request(request: Any) -> bytes:
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return json.dumps(
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            }
        ).encode("utf-8")

    client = OpenAICompatibleEmbeddingClient(http_request=request)
    texts = ["first full asset body", "second full asset body"]

    embeddings = client.embed_texts(
        context=_context(),
        resolution=_resolution(),
        api_key="provider-key",
        texts=texts,
    )

    assert embeddings == [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
    assert captured["url"] == "https://provider.example/v1/embeddings"
    assert captured["body"] == {
        "model": "embedding-model-1",
        "input": texts,
        "dimensions": 3,
    }
    assert captured["headers"]["Authorization"] == "Bearer provider-key"


def test_embedding_client_rejects_inconsistent_dimensions() -> None:
    client = OpenAICompatibleEmbeddingClient(
        http_request=lambda _: json.dumps(
            {
                "data": [
                    {"index": 0, "embedding": [1.0, 0.0]},
                    {"index": 1, "embedding": [0.0, 1.0, 0.0]},
                ]
            }
        ).encode("utf-8")
    )

    with pytest.raises(LLMFacilityError) as exc_info:
        client.embed_texts(
            context=_context(),
            resolution=_resolution(),
            api_key="provider-key",
            texts=["one", "two"],
        )

    assert exc_info.value.code == "SCHEMA_VALIDATION_FAILED"


def test_vector_reindex_requires_llm_facility_embedding_provider() -> None:
    reindexer = PostgresAssetReindexer(connect=lambda: pytest.fail("database must not be called"))

    with pytest.raises(LLMFacilityError) as exc_info:
        reindexer.reindex(context=_context(), scope="project", mode="vector", options={})

    assert exc_info.value.code == "ASSET_EMBEDDING_PROVIDER_UNCONFIGURED"


def test_hybrid_reindex_embeds_full_enabled_assets_and_commits_atomic_swap() -> None:
    asset_rows = [
        ("asset-1", "Rule", "Summary", "Private full content", "2026-07-10 00:00:00+00"),
    ]
    load_connection = ReindexConnection(ReindexCursor(asset_rows=asset_rows))
    swap_cursor = ReindexCursor(asset_rows=asset_rows)
    swap_connection = ReindexConnection(swap_cursor)
    connections = iter([load_connection, swap_connection])
    embedding_client = RecordingEmbeddingClient([[1.0, 0.0, 0.0]])
    reindexer = PostgresAssetReindexer(
        connect=lambda: next(connections),
        binding_resolver=StaticBindingResolver(),
        credential_provider=StaticCredentialProvider(),
        embedding_client=embedding_client,
    )

    result = reindexer.reindex(context=_context(), scope="project", mode="hybrid", options={})

    assert result["status"] == "completed"
    assert result["embedding_count"] == 1
    assert result["embedding_model"] == "embedding-model-1"
    assert embedding_client.calls[0]["texts"] == ["Rule\nSummary\nPrivate full content"]
    assert swap_connection.committed is True
    assert swap_connection.rolled_back is False
    joined_queries = "\n".join(query for query, _ in swap_cursor.executed)
    assert "INSERT INTO global_search_index" in joined_queries
    assert "DELETE FROM asset_embeddings" in joined_queries
    assert "INSERT INTO asset_embeddings" in joined_queries


def test_hybrid_reindex_rolls_back_when_source_changes_before_swap() -> None:
    asset_rows = [
        ("asset-1", "Rule", "Summary", "Private full content", "2026-07-10 00:00:00+00"),
    ]
    load_connection = ReindexConnection(ReindexCursor(asset_rows=asset_rows))
    swap_connection = ReindexConnection(ReindexCursor(asset_rows=asset_rows, source_changed=True))
    connections = iter([load_connection, swap_connection])
    reindexer = PostgresAssetReindexer(
        connect=lambda: next(connections),
        binding_resolver=StaticBindingResolver(),
        credential_provider=StaticCredentialProvider(),
        embedding_client=RecordingEmbeddingClient([[1.0, 0.0, 0.0]]),
    )

    with pytest.raises(LLMFacilityError) as exc_info:
        reindexer.reindex(context=_context(), scope="project", mode="hybrid", options={})

    assert exc_info.value.code == "ASSET_REINDEX_SOURCE_CHANGED"
    assert swap_connection.committed is False
    assert swap_connection.rolled_back is True
