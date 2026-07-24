from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from mirofish_agents.common.context import AgentContext
from mirofish_agents.seed.sequential_reader import (
    AesGcmCredentialDecryptor,
    LLMFacilityError,
    LLMFacilitySequentialReader,
    ModuleBindingResolution,
    OpenAICompatibleJSONClient,
    PostgresCredentialProvider,
    PostgresModuleBindingResolver,
    _chat_request_body,
    _estimate_tokens,
    _segment_batches,
)


def _context() -> AgentContext:
    return AgentContext(
        tenant_id="tenant-1",
        project_id="project-1",
        run_id="run-1",
        workflow_type="seed_pipeline",
        actor_user_id="user-1",
        trace_id="trace-1",
        permissions={"seed_pipeline": ["run"]},
    )


def _resolution() -> ModuleBindingResolution:
    return ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key="sequential_reading",
        channel_id="channel-1",
        model_id="model-a",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-1",
        supports_json=True,
        settings={"temperature": 0.1, "max_tokens": 1200},
    )


def test_llm_facility_sequential_reader_calls_provider_with_explicit_key_and_segment_text() -> None:
    resolver = RecordingBindingResolver(_resolution())
    credentials = RecordingCredentialProvider(api_key="sk-real")
    chat_client = RecordingJSONChatClient(
        response_json={
            "notes": [
                {
                    "segment_id": "segment-1",
                    "summary": "雨夜开场。",
                    "payload_jsonb": {
                        "characters": [],
                        "organizations": [],
                        "relationships": [],
                        "plot_threads": [],
                        "world_rules": [],
                        "events": [],
                        "consistency_notes": [],
                    },
                }
            ]
        }
    )
    object_store = InMemoryObjectStore(
        {"projects/project-1/seed-runs/run-1/segments/0000.txt": "第一章 雨夜\n雨声压住脚步。".encode("utf-8")}
    )
    reader = LLMFacilitySequentialReader(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        segment_text_store=object_store,
    )

    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[
            {
                "segment_id": "segment-1",
                "segment_order": 0,
                "object_key": "projects/project-1/seed-runs/run-1/segments/0000.txt",
                "content": "caller-provided raw text must be ignored",
            }
        ],
    )

    pass_id = result.pop("pass_id")
    UUID(pass_id)
    assert result == {
        "status": "completed",
        "module_key": "sequential_reading",
        "model_id": "model-a",
        "notes": [
            {
                "segment_id": "segment-1",
                "summary": "雨夜开场。",
                "payload_jsonb": {
                    "characters": [],
                    "organizations": [],
                    "relationships": [],
                    "plot_threads": [],
                    "world_rules": [],
                    "events": [],
                    "consistency_notes": [],
                },
            }
        ],
    }
    assert resolver.calls == [("tenant-1", "project-1", "sequential_reading")]
    assert credentials.calls == [("tenant-1", "run-1", "channel-1")]
    assert chat_client.calls[0]["api_key"] == "sk-real"
    assert chat_client.calls[0]["resolution"].model_id == "model-a"
    assert "雨声压住脚步" in chat_client.calls[0]["messages"][1]["content"]
    assert "caller-provided raw text" not in chat_client.calls[0]["messages"][1]["content"]
    assert "content" not in str(result)


def test_llm_facility_sequential_reader_batches_long_segment_lists() -> None:
    class BatchingChatClient:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def complete_json(self, **kwargs: Any) -> dict[str, Any]:
            self.calls.append(kwargs)
            payload = json.loads(kwargs["messages"][1]["content"])
            segment_ids = [item["segment_id"] for item in payload["segments"]]
            return {
                "notes": [
                    {
                        "segment_id": segment_id,
                        "summary": f"note-{segment_id}",
                        "payload_jsonb": {
                            "characters": [],
                            "organizations": [],
                            "relationships": [],
                            "plot_threads": [],
                            "world_rules": [],
                            "events": [],
                            "consistency_notes": [],
                        },
                    }
                    for segment_id in segment_ids
                ]
            }

    base = _resolution()
    resolution = ModuleBindingResolution(
        tenant_id=base.tenant_id,
        project_id=base.project_id,
        module_key=base.module_key,
        channel_id=base.channel_id,
        model_id=base.model_id,
        provider=base.provider,
        base_url=base.base_url,
        credential_ref=base.credential_ref,
        supports_json=base.supports_json,
        settings={"temperature": 0.1, "max_tokens": 1200, "batch_max_segments": 1, "batch_max_chars": 20_000},
    )
    store = InMemoryObjectStore(
        {
            "segments/0000.txt": ("第一章 " + ("甲" * 12_000)).encode("utf-8"),
            "segments/0001.txt": ("第二章 " + ("乙" * 12_000)).encode("utf-8"),
            "segments/0002.txt": ("第三章 " + ("丙" * 12_000)).encode("utf-8"),
        }
    )
    chat_client = BatchingChatClient()
    reader = LLMFacilitySequentialReader(
        binding_resolver=RecordingBindingResolver(resolution),
        credential_provider=RecordingCredentialProvider(api_key="sk-real"),
        chat_client=chat_client,
        segment_text_store=store,
    )

    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[
            {"segment_id": "segment-1", "segment_order": 0, "object_key": "segments/0000.txt"},
            {"segment_id": "segment-2", "segment_order": 1, "object_key": "segments/0001.txt"},
            {"segment_id": "segment-3", "segment_order": 2, "object_key": "segments/0002.txt"},
        ],
    )

    assert result["status"] == "completed"
    assert [note["segment_id"] for note in result["notes"]] == ["segment-1", "segment-2", "segment-3"]
    assert len(chat_client.calls) == 3


def test_llm_facility_sequential_reader_emits_batch_progress_callbacks() -> None:
    base = _resolution()
    resolution = ModuleBindingResolution(
        tenant_id=base.tenant_id,
        project_id=base.project_id,
        module_key=base.module_key,
        channel_id=base.channel_id,
        model_id=base.model_id,
        provider=base.provider,
        base_url=base.base_url,
        credential_ref=base.credential_ref,
        supports_json=base.supports_json,
        settings={"temperature": 0.1, "max_tokens": 1200, "batch_max_segments": 1},
    )
    store = InMemoryObjectStore(
        {
            "segments/0000.txt": "第一章 雨夜".encode("utf-8"),
            "segments/0001.txt": "第二章 晨光".encode("utf-8"),
        }
    )
    class MatchingNotesClient:
        def complete_json(self, **kwargs: Any) -> dict[str, Any]:
            payload = json.loads(kwargs["messages"][1]["content"])
            segment_id = payload["segments"][0]["segment_id"]
            return {
                "notes": [
                    {
                        "segment_id": segment_id,
                        "summary": f"note-{segment_id}",
                        "payload_jsonb": {
                            "characters": [],
                            "organizations": [],
                            "relationships": [],
                            "plot_threads": [],
                            "world_rules": [],
                            "events": [],
                            "consistency_notes": [],
                        },
                    }
                ]
            }

    events: list[dict[str, Any]] = []
    reader = LLMFacilitySequentialReader(
        binding_resolver=RecordingBindingResolver(resolution),
        credential_provider=RecordingCredentialProvider(api_key="sk-real"),
        chat_client=MatchingNotesClient(),
        segment_text_store=store,
    )
    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[
            {
                "segment_id": "segment-1",
                "segment_order": 0,
                "object_key": "segments/0000.txt",
                "title_guess": "第一章 雨夜",
            },
            {
                "segment_id": "segment-2",
                "segment_order": 1,
                "object_key": "segments/0001.txt",
                "title_guess": "第二章 晨光",
            },
        ],
        progress_callback=events.append,
    )

    assert result["status"] == "completed"
    phases = [item["phase"] for item in events]
    assert phases == ["batch_start", "batch_completed", "batch_start", "batch_completed"]
    assert events[0]["total_segments"] == 2
    assert events[0]["completed_segments"] == 0
    assert "第一章 雨夜" in events[0]["message"]
    assert events[1]["completed_segments"] == 1
    assert events[-1]["completed_segments"] == 2
    assert "object_key" not in str(events)
    assert "content" not in str(events)


def test_llm_facility_sequential_reader_fails_closed_when_module_is_unbound() -> None:
    resolver = RecordingBindingResolver(LLMFacilityError("LLM_MODULE_UNBOUND", "sequential_reading module is not bound"))
    credentials = RecordingCredentialProvider(api_key="sk-real")
    chat_client = RecordingJSONChatClient(response_json={"notes": []})
    reader = LLMFacilitySequentialReader(
        binding_resolver=resolver,
        credential_provider=credentials,
        chat_client=chat_client,
        segment_text_store=InMemoryObjectStore({"segments/0000.txt": b"text"}),
    )

    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[{"segment_id": "segment-1", "segment_order": 0, "object_key": "segments/0000.txt"}],
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_MODULE_UNBOUND"
    assert credentials.calls == []
    assert chat_client.calls == []


def test_llm_facility_sequential_reader_fails_closed_when_credential_is_unavailable() -> None:
    reader = LLMFacilitySequentialReader(
        binding_resolver=RecordingBindingResolver(_resolution()),
        credential_provider=RecordingCredentialProvider(
            error=LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "credential is unavailable")
        ),
        chat_client=RecordingJSONChatClient(response_json={"notes": []}),
        segment_text_store=InMemoryObjectStore({"segments/0000.txt": b"text"}),
    )

    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[{"segment_id": "segment-1", "segment_order": 0, "object_key": "segments/0000.txt"}],
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_CREDENTIAL_UNAVAILABLE"


def test_llm_facility_sequential_reader_rejects_resolution_without_provider_before_credential_call() -> None:
    resolution = _resolution()
    reader = LLMFacilitySequentialReader(
        binding_resolver=RecordingBindingResolver(
            ModuleBindingResolution(
                tenant_id=resolution.tenant_id,
                project_id=resolution.project_id,
                module_key=resolution.module_key,
                channel_id=resolution.channel_id,
                model_id=resolution.model_id,
                provider="",
                base_url=resolution.base_url,
                credential_ref=resolution.credential_ref,
                supports_json=resolution.supports_json,
                settings=resolution.settings,
            )
        ),
        credential_provider=RecordingCredentialProvider(api_key="sk-real"),
        chat_client=RecordingJSONChatClient(response_json={"notes": []}),
        segment_text_store=InMemoryObjectStore({"segments/0000.txt": b"text"}),
    )

    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[{"segment_id": "segment-1", "segment_order": 0, "object_key": "segments/0000.txt"}],
    )

    assert result == {
        "status": "failed",
        "error": {
            "code": "LLM_PROVIDER_ERROR",
            "message": "resolved LLM module is missing provider",
        },
        "module_key": "sequential_reading",
    }
    credential_provider = reader._credential_provider
    chat_client = reader._chat_client
    assert isinstance(credential_provider, RecordingCredentialProvider)
    assert isinstance(chat_client, RecordingJSONChatClient)
    assert credential_provider.calls == []
    assert chat_client.calls == []


def test_openai_compatible_json_client_sends_explicit_key_and_parses_json_content() -> None:
    transport = RecordingHTTPTransport(
        response_body=json.dumps(
            {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "notes": [
                                        {
                                            "segment_id": "segment-1",
                                            "summary": "段落概要",
                                            "payload_jsonb": {"characters": []},
                                        }
                                    ]
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 13,
                    "completion_tokens": 21,
                    "total_tokens": 34,
                    "cost_estimate": 0.0042,
                },
            }
        ).encode("utf-8")
    )
    client = OpenAICompatibleJSONClient(http_request=transport)

    result = client.complete_json(
        context=_context(),
        resolution=_resolution(),
        api_key="sk-real",
        messages=[{"role": "user", "content": "return JSON"}],
    )

    assert result["notes"][0]["summary"] == "段落概要"
    assert result["__llm_usage"] == {
        "prompt_tokens": 13,
        "completion_tokens": 21,
        "total_tokens": 34,
        "cost_estimate": 0.0042,
    }
    request = transport.requests[0]
    assert request.full_url == "https://llm.example/v1/chat/completions"
    assert request.get_method() == "POST"
    assert request.headers["Authorization"] == "Bearer sk-real"
    request_body = json.loads(request.data.decode("utf-8"))
    assert request_body["model"] == "model-a"
    assert request_body["response_format"] == {"type": "json_object"}
    assert request_body["temperature"] == 0.1
    assert request_body["max_tokens"] == 1200


def test_openai_compatible_json_client_parses_markdown_fenced_json_content() -> None:
    fenced = (
        "以下是结果：\n```json\n"
        + json.dumps(
            {
                "notes": [
                    {
                        "segment_id": "segment-1",
                        "summary": "围栏 JSON",
                        "payload_jsonb": {"characters": []},
                    }
                ]
            },
            ensure_ascii=False,
        )
        + "\n```\n"
    )
    transport = RecordingHTTPTransport(
        response_body=json.dumps({"choices": [{"message": {"content": fenced}}]}).encode("utf-8")
    )
    client = OpenAICompatibleJSONClient(http_request=transport)

    result = client.complete_json(
        context=_context(),
        resolution=_resolution(),
        api_key="sk-real",
        messages=[{"role": "user", "content": "return JSON"}],
    )

    assert result["notes"][0]["summary"] == "围栏 JSON"


def test_llm_facility_sequential_reader_retries_and_splits_invalid_json_batches() -> None:
    base = _resolution()
    resolution = ModuleBindingResolution(
        tenant_id=base.tenant_id,
        project_id=base.project_id,
        module_key=base.module_key,
        channel_id=base.channel_id,
        model_id=base.model_id,
        provider=base.provider,
        base_url=base.base_url,
        credential_ref=base.credential_ref,
        supports_json=base.supports_json,
        settings={"temperature": 0.1, "max_tokens": 1200, "batch_max_segments": 2},
    )
    store = InMemoryObjectStore(
        {
            "segments/0000.txt": "第一章 雨夜".encode("utf-8"),
            "segments/0001.txt": "第二章 晨光".encode("utf-8"),
        }
    )

    class FlakyThenSplitClient:
        def __init__(self) -> None:
            self.calls: list[list[str]] = []

        def complete_json(self, **kwargs: Any) -> dict[str, Any]:
            payload = json.loads(kwargs["messages"][1]["content"])
            segment_ids = [item["segment_id"] for item in payload["segments"]]
            self.calls.append(segment_ids)
            # First two attempts on the 2-segment batch fail (retry + split trigger).
            if len(segment_ids) == 2:
                raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion content was not valid JSON")
            return {
                "notes": [
                    {
                        "segment_id": segment_ids[0],
                        "summary": f"note-{segment_ids[0]}",
                        "payload_jsonb": {
                            "characters": [],
                            "organizations": [],
                            "relationships": [],
                            "plot_threads": [],
                            "world_rules": [],
                            "events": [],
                            "consistency_notes": [],
                        },
                    }
                ]
            }

    events: list[dict[str, Any]] = []
    chat_client = FlakyThenSplitClient()
    reader = LLMFacilitySequentialReader(
        binding_resolver=RecordingBindingResolver(resolution),
        credential_provider=RecordingCredentialProvider(api_key="sk-real"),
        chat_client=chat_client,
        segment_text_store=store,
    )
    result = reader.read_segments(
        context=_context(),
        module_key="sequential_reading",
        segments=[
            {
                "segment_id": "segment-1",
                "segment_order": 0,
                "object_key": "segments/0000.txt",
                "title_guess": "第一章 雨夜",
            },
            {
                "segment_id": "segment-2",
                "segment_order": 1,
                "object_key": "segments/0001.txt",
                "title_guess": "第二章 晨光",
            },
        ],
        progress_callback=events.append,
    )

    assert result["status"] == "completed"
    assert [note["segment_id"] for note in result["notes"]] == ["segment-1", "segment-2"]
    # 2 failing full-batch attempts + 1 per half after split.
    assert chat_client.calls == [
        ["segment-1", "segment-2"],
        ["segment-1", "segment-2"],
        ["segment-1"],
        ["segment-2"],
    ]
    phases = [item["phase"] for item in events]
    assert "batch_retry" in phases
    assert "batch_split" in phases
    assert phases[-1] == "batch_completed"


def test_postgres_module_binding_resolver_resolves_project_binding_without_credential_material() -> None:
    connection = QueryConnection(
        rows=[
            {
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "module_key": "sequential_reading",
                "channel_id": "channel-project",
                "model_id": "model-json",
                "provider": "openai-compatible",
                "base_url": "https://llm.example/v1",
                "supports_json": True,
                "settings_jsonb": '{"temperature":0.2}',
            }
        ]
    )
    resolver = PostgresModuleBindingResolver(connect=lambda: connection)

    resolution = resolver.resolve_module_binding(context=_context(), module_key="sequential_reading")

    assert resolution == ModuleBindingResolution(
        tenant_id="tenant-1",
        project_id="project-1",
        module_key="sequential_reading",
        channel_id="channel-project",
        model_id="model-json",
        provider="openai-compatible",
        base_url="https://llm.example/v1",
        credential_ref="channel-project",
        supports_json=True,
        settings={"temperature": 0.2},
    )
    assert "encrypted_api_key" not in connection.cursor_instance.query.lower()
    assert "api_key" not in connection.cursor_instance.query.lower()
    assert "llm_platform_module_defaults" in connection.cursor_instance.query
    assert "UNION ALL" in connection.cursor_instance.query
    assert "2 AS binding_rank" in connection.cursor_instance.query
    assert connection.cursor_instance.query.count("m.enabled = TRUE") == 2
    assert connection.cursor_instance.params == ("tenant-1", "project-1", "sequential_reading")
    assert connection.closed is True


def test_postgres_module_binding_resolver_infers_json_for_chat_models_with_false_catalog() -> None:
    """Stale supports_json=false must not block DeepSeek-class chat models."""
    connection = QueryConnection(
        rows=[
            {
                "tenant_id": "tenant-1",
                "project_id": "project-1",
                "module_key": "sequential_reading",
                "channel_id": "channel-project",
                "model_id": "deepseek-v4-flash",
                "provider": "openai-compatible",
                "base_url": "https://api.deepseek.com/v1",
                "supports_json": False,
                "settings_jsonb": "{}",
            }
        ]
    )
    resolver = PostgresModuleBindingResolver(connect=lambda: connection)

    resolution = resolver.resolve_module_binding(context=_context(), module_key="sequential_reading")

    assert resolution.model_id == "deepseek-v4-flash"
    assert resolution.supports_json is True


def test_postgres_module_binding_resolver_fails_closed_when_unbound() -> None:
    resolver = PostgresModuleBindingResolver(connect=lambda: QueryConnection(rows=[]))

    try:
        resolver.resolve_module_binding(context=_context(), module_key="sequential_reading")
    except LLMFacilityError as exc:
        assert exc.code == "LLM_MODULE_UNBOUND"
        assert "sequential_reading" in exc.message
    else:
        raise AssertionError("expected LLM_MODULE_UNBOUND")


def test_postgres_module_binding_resolver_sanitizes_query_exception_message() -> None:
    connection = FailingQueryConnection(
        RuntimeError("binding query leaked prompt=隐藏指令 api_key=sk-nope credential_ref=secret")
    )
    resolver = PostgresModuleBindingResolver(connect=lambda: connection)
    public_message = ""

    try:
        resolver.resolve_module_binding(context=_context(), module_key="sequential_reading")
    except LLMFacilityError as exc:
        assert exc.code == "LLM_BINDING_QUERY_FAILED"
        assert exc.message == "LLM module binding query failed"
        public_message = exc.message
    else:
        raise AssertionError("expected LLM_BINDING_QUERY_FAILED")

    assert connection.closed is True
    encoded = json.dumps({"message": public_message}, ensure_ascii=False)
    for forbidden in ["隐藏指令", "sk-nope", "prompt=", "api_key", "credential_ref", "secret"]:
        assert forbidden not in encoded


def test_postgres_credential_provider_decrypts_supported_aes_gcm_envelope() -> None:
    connection = QueryConnection(
        rows=[
            {
                "encrypted_api_key": (
                    "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                    "87utEhTfLrnKAiv0vtWdTg==:qe3dwCoCLzMECbZ5"
                )
            }
        ]
    )
    decryptor = AesGcmCredentialDecryptor(
        key_material="000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    )
    provider = PostgresCredentialProvider(connect=lambda: connection, decryptor=decryptor)

    api_key = provider.resolve_api_key(context=_context(), credential_ref="channel-project")

    assert api_key == "sk-seed-live"
    assert "encrypted_api_key" in connection.cursor_instance.query
    assert connection.cursor_instance.params == ("channel-project", "tenant-1")
    assert connection.closed is True


def test_postgres_credential_provider_fails_closed_when_key_is_unconfigured() -> None:
    provider = PostgresCredentialProvider(connect=lambda: QueryConnection(rows=[]), decryptor=None)

    try:
        provider.resolve_api_key(context=_context(), credential_ref="channel-project")
    except LLMFacilityError as exc:
        assert exc.code == "LLM_CREDENTIAL_KEY_UNCONFIGURED"
    else:
        raise AssertionError("expected LLM_CREDENTIAL_KEY_UNCONFIGURED")


def test_postgres_credential_provider_sanitizes_query_exception_message() -> None:
    connection = FailingQueryConnection(
        RuntimeError("credential query leaked prompt=隐藏指令 api_key=sk-nope credential_ref=secret")
    )
    decryptor = AesGcmCredentialDecryptor(
        key_material="000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    )
    provider = PostgresCredentialProvider(connect=lambda: connection, decryptor=decryptor)
    public_message = ""

    try:
        provider.resolve_api_key(context=_context(), credential_ref="channel-project")
    except LLMFacilityError as exc:
        assert exc.code == "LLM_CREDENTIAL_QUERY_FAILED"
        assert exc.message == "LLM credential query failed"
        public_message = exc.message
    else:
        raise AssertionError("expected LLM_CREDENTIAL_QUERY_FAILED")

    assert connection.closed is True
    encoded = json.dumps({"message": public_message}, ensure_ascii=False)
    for forbidden in ["隐藏指令", "sk-nope", "prompt=", "api_key", "credential_ref", "secret"]:
        assert forbidden not in encoded


def test_postgres_credential_provider_fails_closed_for_bad_envelope() -> None:
    connection = QueryConnection(rows=[{"encrypted_api_key": "aes-256-gcm:v1:not-base64:tag:cipher"}])
    decryptor = AesGcmCredentialDecryptor(
        key_material="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
    )
    provider = PostgresCredentialProvider(connect=lambda: connection, decryptor=decryptor)

    try:
        provider.resolve_api_key(context=_context(), credential_ref="channel-project")
    except LLMFacilityError as exc:
        assert exc.code == "LLM_CREDENTIAL_UNAVAILABLE"
    else:
        raise AssertionError("expected LLM_CREDENTIAL_UNAVAILABLE")


def test_postgres_credential_provider_fails_closed_for_authentication_failure() -> None:
    connection = QueryConnection(
        rows=[
            {
                "encrypted_api_key": (
                    "aes-256-gcm:v1:ABEiM0RVZneImaq7:"
                    "AAAAAAAAAAAAAAAAAAAAAA==:qe3dwCoCLzMECbZ5"
                )
            }
        ]
    )
    decryptor = AesGcmCredentialDecryptor(
        key_material="000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f"
    )
    provider = PostgresCredentialProvider(connect=lambda: connection, decryptor=decryptor)

    try:
        provider.resolve_api_key(context=_context(), credential_ref="channel-project")
    except LLMFacilityError as exc:
        assert exc.code == "LLM_CREDENTIAL_DECRYPT_FAILED"
    else:
        raise AssertionError("expected LLM_CREDENTIAL_DECRYPT_FAILED")


class RecordingBindingResolver:
    def __init__(self, result: ModuleBindingResolution | LLMFacilityError) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None, str]] = []

    def resolve_module_binding(self, *, context: AgentContext, module_key: str) -> ModuleBindingResolution:
        self.calls.append((context.tenant_id, context.project_id, module_key))
        if isinstance(self.result, LLMFacilityError):
            raise self.result
        return self.result


class RecordingCredentialProvider:
    def __init__(self, api_key: str | None = None, error: LLMFacilityError | None = None) -> None:
        self.api_key = api_key
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        self.calls.append((context.tenant_id, context.run_id, credential_ref))
        if self.error is not None:
            raise self.error
        assert self.api_key is not None
        return self.api_key


class RecordingJSONChatClient:
    def __init__(self, response_json: dict[str, Any]) -> None:
        self.response_json = response_json
        self.calls: list[dict[str, Any]] = []

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "context": context,
                "resolution": resolution,
                "api_key": api_key,
                "messages": messages,
            }
        )
        return self.response_json


class InMemoryObjectStore:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects

    def read_bytes(self, object_key: str) -> bytes:
        return self.objects[object_key]


class RecordingHTTPTransport:
    def __init__(self, response_body: bytes) -> None:
        self.response_body = response_body
        self.requests: list[object] = []

    def __call__(self, request: object) -> bytes:
        self.requests.append(request)
        return self.response_body


class QueryCursor:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.query = ""
        self.params: tuple[object, ...] = ()

    def __enter__(self) -> "QueryCursor":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        self.query = query
        self.params = params

    def fetchone(self) -> dict[str, Any] | None:
        if not self.rows:
            return None
        return self.rows[0]


class QueryConnection:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.cursor_instance = QueryCursor(rows)
        self.closed = False

    def cursor(self) -> QueryCursor:
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class FailingQueryCursor(QueryCursor):
    def __init__(self, error: Exception) -> None:
        super().__init__([])
        self.error = error

    def execute(self, query: str, params: tuple[object, ...]) -> None:
        super().execute(query, params)
        raise self.error


class FailingQueryConnection(QueryConnection):
    def __init__(self, error: Exception) -> None:
        self.cursor_instance = FailingQueryCursor(error)
        self.closed = False


# ── Token-aware batching + output budget (seed read robustness) ──────────────


def test_estimate_tokens_counts_cjk_heavier_than_latin() -> None:
    # ~1.5 tokens per CJK char, ~0.25 per latin char, plus a small +1 safety margin.
    assert _estimate_tokens("甲乙丙丁") == 7  # int(4 * 1.5) + 1
    assert _estimate_tokens("abcd") == 2  # int(4 * 0.25) + 1
    assert _estimate_tokens("") >= 1
    assert _estimate_tokens("甲乙丙丁") > _estimate_tokens("abcd")


def test_segment_batches_default_token_budget_packs_chapters_together() -> None:
    # 4 small chapters (~1200 chars each ≈ 1800 tokens) all fit under the 60k
    # default token budget and share chapters, so they must batch into ONE call,
    # but a new chapter never splits mid-chapter.
    store = InMemoryObjectStore({f"segments/{i:04d}.txt": ("正文" * 600).encode("utf-8") for i in range(4)})
    segments = [
        {"segment_id": f"segment-{i}", "segment_order": i, "object_key": f"segments/{i:04d}.txt", "chapter_guess": f"第{i}章"}
        for i in range(4)
    ]
    batches = _segment_batches(segments, segment_text_store=store, settings={})
    # Default budget 60k tokens >> these; but chapter boundaries force one batch
    # per chapter (whole-chapter reads), so 4 chapters -> 4 batches, never split.
    assert len(batches) == 4
    assert all(len(batch) == 1 for batch in batches)


def test_segment_batches_respects_configured_token_budget() -> None:
    # A tight token budget forces packing: each ~1800-token chapter, budget 4000
    # -> two chapters per batch until the budget would overflow.
    store = InMemoryObjectStore({f"segments/{i:04d}.txt": ("正文" * 600).encode("utf-8") for i in range(4)})
    segments = [
        {"segment_id": f"segment-{i}", "segment_order": i, "object_key": f"segments/{i:04d}.txt"}
        for i in range(4)  # no chapter_guess -> chapter rule inert, token budget governs
    ]
    batches = _segment_batches(segments, segment_text_store=store, settings={"batch_max_tokens": 4000})
    # 4 chapters * ~1800 tokens, budget 4000 -> 2 per batch -> 2 batches.
    assert [len(batch) for batch in batches] == [2, 2]


def test_chat_request_body_defaults_max_tokens_for_large_batches() -> None:
    # No explicit max_tokens in settings -> a generous default output budget is
    # sent so a 60k-token batch's notes are not truncated mid-JSON.
    base = _resolution()
    resolution = ModuleBindingResolution(
        tenant_id=base.tenant_id, project_id=base.project_id, module_key=base.module_key,
        channel_id=base.channel_id, model_id=base.model_id, provider=base.provider,
        base_url=base.base_url, credential_ref=base.credential_ref, supports_json=base.supports_json,
        settings={"temperature": 0.1},  # no max_tokens
    )
    body = _chat_request_body(resolution, [{"role": "user", "content": "x"}])
    assert body["max_tokens"] == 30_000
    assert body["response_format"] == {"type": "json_object"}
    # Explicit setting still wins.
    base2 = _resolution()
    body2 = _chat_request_body(base2, [{"role": "user", "content": "x"}])
    assert body2["max_tokens"] == 1200
