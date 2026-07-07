from __future__ import annotations

import json
from typing import Any, Callable, Protocol

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import (
    CredentialProvider,
    JSONChatClient,
    LLMFacilityError,
    ModuleBindingResolution,
    ModuleBindingResolver,
    set_postgres_tenant_context,
)


GLOBAL_AGGREGATION_MODULE_KEY = "anchor_point_summary"
SENSITIVE_AGGREGATE_KEYS = {
    "api_key",
    "body",
    "content",
    "credential_ref",
    "encrypted_api_key",
    "evidence",
    "evidence_text",
    "prompt",
    "raw_content",
    "response",
    "text",
}


class SeedAggregateSource(Protocol):
    def load_aggregate_input(self, *, context: AgentContext) -> dict[str, Any]:
        """Load public seed aggregation inputs under tenant/project/run scope."""


class PostgresSeedAggregateSource:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresSeedAggregateSource":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL seed aggregation") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def load_aggregate_input(self, *, context: AgentContext) -> dict[str, Any]:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required for seed aggregation")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT segment_id::text AS segment_id, summary
                       FROM segment_summaries
                       WHERE tenant_id = %s
                         AND project_id = %s
                         AND run_id = %s
                       ORDER BY created_at ASC""",
                    (context.tenant_id, context.project_id, context.run_id),
                )
                segment_rows = cursor.fetchall()
                cursor.execute(
                    """WITH input(tenant_id, project_id, run_id) AS (
                         VALUES (%s, %s, %s)
                       )
                       SELECT 'entities' AS fact_type, COUNT(*)::int AS fact_count
                       FROM entities e, input i
                       WHERE e.tenant_id::text = i.tenant_id
                         AND e.project_id::text = i.project_id
                         AND e.run_id::text = i.run_id
                       UNION ALL
                       SELECT 'relationships' AS fact_type, COUNT(*)::int AS fact_count
                       FROM relationships r, input i
                       WHERE r.tenant_id::text = i.tenant_id
                         AND r.project_id::text = i.project_id
                         AND r.run_id::text = i.run_id""",
                    (context.tenant_id, context.project_id, context.run_id),
                )
                count_rows = cursor.fetchall()
        except LLMFacilityError:
            raise
        except Exception as exc:
            raise LLMFacilityError(
                "SEED_AGGREGATE_SOURCE_QUERY_FAILED",
                "seed aggregate source query failed",
            ) from exc
        finally:
            connection.close()

        return {
            "segment_summaries": [
                {
                    "segment_id": _row_text(row, 0, "segment_id"),
                    "summary": _row_text(row, 1, "summary"),
                }
                for row in segment_rows
                if _row_text(row, 0, "segment_id") and _row_text(row, 1, "summary")
            ],
            "fact_counts": {
                _row_text(row, 0, "fact_type"): _row_int(row, 1, "fact_count")
                for row in count_rows
                if _row_text(row, 0, "fact_type")
            },
        }


class LLMFacilityGlobalAggregator:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        aggregate_source: SeedAggregateSource,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._aggregate_source = aggregate_source

    def aggregate(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> dict[str, Any]:
        if module_key != GLOBAL_AGGREGATION_MODULE_KEY:
            return _failed("VALIDATION_FAILED", "LLMFacilityGlobalAggregator only supports anchor_point_summary")
        try:
            resolution = self._binding_resolver.resolve_module_binding(
                context=context,
                module_key=module_key,
            )
            _validate_resolution(resolution)
            api_key = self._credential_provider.resolve_api_key(
                context=context,
                credential_ref=resolution.credential_ref,
            )
            if not isinstance(api_key, str) or not api_key.strip():
                raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "resolved credential was empty")
            aggregate_input = _sanitize_aggregate_input(self._aggregate_source.load_aggregate_input(context=context))
            response_json = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key.strip(),
                messages=_global_aggregation_messages(context=context, aggregate_input=aggregate_input),
            )
            seed_analysis = response_json.get("seed_analysis")
            if not isinstance(seed_analysis, dict):
                raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "seed_analysis must be a JSON object")
        except LLMFacilityError as exc:
            return _failed(exc.code, exc.message)
        except Exception as exc:
            return _failed("LLM_PROVIDER_ERROR", str(exc))

        return {
            "status": "completed",
            "module_key": module_key,
            "model_id": resolution.model_id,
            "segment_count": _segment_count(aggregate_input),
            "summary_count": _summary_count(seed_analysis),
            "seed_analysis": seed_analysis,
        }


def _validate_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != GLOBAL_AGGREGATION_MODULE_KEY:
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match anchor_point_summary")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_MODULE_CAPABILITY_MISSING", "anchor_point_summary requires a JSON-capable model")
    for field_name in ("channel_id", "model_id", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _global_aggregation_messages(
    *,
    context: AgentContext,
    aggregate_input: dict[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish seed global aggregation module. Return one JSON object with "
                "seed_analysis as an object. Use only the supplied public summaries and fact counts. "
                "Do not include raw text, evidence, prompt bodies, API keys, or provider metadata."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": GLOBAL_AGGREGATION_MODULE_KEY,
                    "aggregate_input": aggregate_input,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _sanitize_aggregate_input(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _sanitize_aggregate_input(child)
            for key, child in value.items()
            if str(key).lower() not in SENSITIVE_AGGREGATE_KEYS
        }
    if isinstance(value, list):
        return [_sanitize_aggregate_input(item) for item in value]
    return value


def _segment_count(aggregate_input: dict[str, Any]) -> int:
    summaries = aggregate_input.get("segment_summaries")
    return len(summaries) if isinstance(summaries, list) else 0


def _summary_count(seed_analysis: dict[str, Any]) -> int:
    return sum(1 for value in seed_analysis.values() if isinstance(value, str) and value.strip())


def _failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "module_key": GLOBAL_AGGREGATION_MODULE_KEY,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _row_text(row: Any, index: int, key: str) -> str:
    if isinstance(row, dict):
        value = row.get(key)
    else:
        value = row[index]
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()


def _row_int(row: Any, index: int, key: str) -> int:
    if isinstance(row, dict):
        value = row.get(key)
    else:
        value = row[index]
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0
