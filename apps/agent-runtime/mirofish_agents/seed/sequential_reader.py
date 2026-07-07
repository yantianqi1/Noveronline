from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen
from uuid import UUID

from mirofish_agents.common.context import AgentContext


@dataclass(frozen=True)
class ModuleBindingResolution:
    tenant_id: str
    project_id: str | None
    module_key: str
    channel_id: str
    model_id: str
    provider: str
    base_url: str
    credential_ref: str
    supports_json: bool
    settings: dict[str, Any] = field(default_factory=dict)


class LLMFacilityError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ModuleBindingResolver(Protocol):
    def resolve_module_binding(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> ModuleBindingResolution:
        """Resolve a module through LLM Facility under the current tenant/project."""


class CredentialProvider(Protocol):
    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        """Return the per-request provider key for a resolved LLM Facility credential ref."""


class JSONChatClient(Protocol):
    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        """Call the resolved provider and return parsed JSON output."""


class SegmentTextStore(Protocol):
    def read_bytes(self, object_key: str) -> bytes:
        """Read private segment text bytes from object storage."""


class PostgresModuleBindingResolver:
    def __init__(self, *, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresModuleBindingResolver":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL LLM binding resolution") from exc

        return cls(connect=lambda: psycopg.connect(database_url))

    def resolve_module_binding(
        self,
        *,
        context: AgentContext,
        module_key: str,
    ) -> ModuleBindingResolution:
        if not context.project_id:
            raise LLMFacilityError("VALIDATION_FAILED", "project_id is required to resolve LLM module bindings")
        normalized_module_key = _required_text(module_key, "module_key")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """WITH input(tenant_id, project_id, module_key) AS (
                         VALUES (%s, %s, %s)
                       )
                       SELECT
                         tenant_id::text AS tenant_id,
                         COALESCE(project_id::text, '') AS project_id,
                         module_key,
                         channel_id::text AS channel_id,
                         model_id,
                         provider,
                         base_url,
                         supports_json,
                         settings_jsonb::text AS settings_jsonb
                       FROM (
                         SELECT
                           b.tenant_id,
                           b.project_id,
                           b.module_key,
                           b.channel_id,
                           b.model_id,
                           c.provider,
                           c.base_url,
                           COALESCE(m.supports_json, false) AS supports_json,
                           b.settings_jsonb,
                           CASE WHEN b.project_id::text = i.project_id THEN 0 ELSE 1 END AS binding_rank
                         FROM llm_module_bindings b
                         JOIN input i ON TRUE
                         JOIN llm_channels c
                           ON c.channel_id = b.channel_id
                          AND c.enabled = TRUE
                          AND (c.tenant_id = b.tenant_id OR c.tenant_id IS NULL)
                         JOIN llm_models m
                          ON m.channel_id = b.channel_id
                          AND m.model_id = b.model_id
                          AND (m.tenant_id = b.tenant_id OR m.tenant_id IS NULL)
                         WHERE b.tenant_id::text = i.tenant_id
                           AND (b.project_id::text = i.project_id OR b.project_id IS NULL)
                           AND b.module_key = i.module_key
                       ) ranked_bindings
                       ORDER BY binding_rank, module_key
                       LIMIT 1""",
                    (context.tenant_id, context.project_id, normalized_module_key),
                )
                row = cursor.fetchone()
        except LLMFacilityError:
            raise
        except Exception as exc:
            raise LLMFacilityError("LLM_BINDING_QUERY_FAILED", "LLM module binding query failed") from exc
        finally:
            connection.close()
        if row is None:
            raise LLMFacilityError("LLM_MODULE_UNBOUND", f"{normalized_module_key} module is not bound")
        return ModuleBindingResolution(
            tenant_id=_row_value(row, 0, "tenant_id"),
            project_id=_row_value(row, 1, "project_id") or None,
            module_key=_row_value(row, 2, "module_key"),
            channel_id=_row_value(row, 3, "channel_id"),
            model_id=_row_value(row, 4, "model_id"),
            provider=_row_value(row, 5, "provider"),
            base_url=_row_value(row, 6, "base_url"),
            credential_ref=_row_value(row, 3, "channel_id"),
            supports_json=_row_bool(row, 7, "supports_json"),
            settings=_settings_from_row(row, 8, "settings_jsonb"),
        )


class AesGcmCredentialDecryptor:
    def __init__(self, *, key_material: str) -> None:
        self._key = _parse_aes_256_key(key_material)

    def decrypt(self, envelope: str) -> str:
        algorithm, version, iv, auth_tag, ciphertext = _parse_aes_gcm_envelope(envelope)
        if algorithm != "aes-256-gcm" or version != "v1":
            raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "unsupported credential cipher")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:  # pragma: no cover - packaging regression guard
            raise LLMFacilityError("LLM_CREDENTIAL_DECRYPTOR_UNAVAILABLE", "cryptography is required") from exc
        try:
            plaintext = AESGCM(self._key).decrypt(iv, ciphertext + auth_tag, None)
            return plaintext.decode("utf-8")
        except Exception as exc:
            raise LLMFacilityError("LLM_CREDENTIAL_DECRYPT_FAILED", "credential decrypt failed") from exc


class PostgresCredentialProvider:
    def __init__(
        self,
        *,
        connect: Callable[[], Any],
        decryptor: AesGcmCredentialDecryptor | None,
    ) -> None:
        self._connect = connect
        self._decryptor = decryptor

    @classmethod
    def from_database_url(
        cls,
        *,
        database_url: str,
        key_material: str | None,
    ) -> "PostgresCredentialProvider":
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on runtime packaging
            raise RuntimeError("psycopg is required for DATABASE_URL LLM credential resolution") from exc
        decryptor = AesGcmCredentialDecryptor(key_material=key_material) if key_material else None
        return cls(connect=lambda: psycopg.connect(database_url), decryptor=decryptor)

    def resolve_api_key(self, *, context: AgentContext, credential_ref: str) -> str:
        if self._decryptor is None:
            raise LLMFacilityError(
                "LLM_CREDENTIAL_KEY_UNCONFIGURED",
                "LLM_CREDENTIAL_ENCRYPTION_KEY is required to decrypt LLM Facility credentials",
            )
        normalized_credential_ref = _required_text(credential_ref, "credential_ref")
        connection = self._connect()
        try:
            set_postgres_tenant_context(connection, context=context)
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT encrypted_api_key
                       FROM llm_channels
                       WHERE channel_id::text = %s
                         AND enabled = TRUE
                         AND (tenant_id::text = %s OR tenant_id IS NULL)
                       ORDER BY tenant_id NULLS LAST
                       LIMIT 1""",
                    (normalized_credential_ref, context.tenant_id),
                )
                row = cursor.fetchone()
        except LLMFacilityError:
            raise
        except Exception as exc:
            raise LLMFacilityError("LLM_CREDENTIAL_QUERY_FAILED", "LLM credential query failed") from exc
        finally:
            connection.close()
        if row is None:
            raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "credential reference is not available")
        encrypted_api_key = _row_value(row, 0, "encrypted_api_key")
        api_key = self._decryptor.decrypt(encrypted_api_key)
        if not isinstance(api_key, str) or not api_key.strip():
            raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "decrypted credential was empty")
        return api_key.strip()


def set_postgres_tenant_context(connection: Any, *, context: AgentContext) -> None:
    tenant_id = _uuid_text_or_none(context.tenant_id)
    if tenant_id is None:
        return
    actor_user_id = _uuid_text_or_none(context.actor_user_id)
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT app_set_tenant_context(%s::uuid, %s::uuid, false)",
            (tenant_id, actor_user_id),
        )


class LLMFacilitySequentialReader:
    def __init__(
        self,
        *,
        binding_resolver: ModuleBindingResolver,
        credential_provider: CredentialProvider,
        chat_client: JSONChatClient,
        segment_text_store: SegmentTextStore,
    ) -> None:
        self._binding_resolver = binding_resolver
        self._credential_provider = credential_provider
        self._chat_client = chat_client
        self._segment_text_store = segment_text_store

    def read_segments(
        self,
        *,
        context: AgentContext,
        module_key: str,
        segments: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if module_key != "sequential_reading":
            return _failed("VALIDATION_FAILED", "LLMFacilitySequentialReader only supports sequential_reading")
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
            messages = _sequential_reading_messages(
                context=context,
                segments=segments,
                segment_text_store=self._segment_text_store,
            )
            response_json = self._chat_client.complete_json(
                context=context,
                resolution=resolution,
                api_key=api_key.strip(),
                messages=messages,
            )
        except LLMFacilityError as exc:
            return _failed(exc.code, exc.message)
        except Exception as exc:
            return _failed("LLM_PROVIDER_ERROR", str(exc))

        return {
            "status": "completed",
            "pass_id": f"{context.run_id}:sequential_reading",
            "module_key": module_key,
            "model_id": resolution.model_id,
            "notes": response_json.get("notes", []),
        }


class OpenAICompatibleJSONClient:
    def __init__(self, *, http_request: Callable[[Request], bytes] | None = None) -> None:
        self._http_request = http_request or _urlopen_bytes

    def complete_json(
        self,
        *,
        context: AgentContext,
        resolution: ModuleBindingResolution,
        api_key: str,
        messages: list[dict[str, str]],
    ) -> dict[str, Any]:
        request = Request(
            _chat_completions_url(resolution.base_url),
            data=json.dumps(_chat_request_body(resolution, messages), ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-MiroFish-Tenant-Id": context.tenant_id,
                "X-MiroFish-Project-Id": context.project_id or "",
                "X-MiroFish-Run-Id": context.run_id,
                "X-MiroFish-Module-Key": resolution.module_key,
            },
            method="POST",
        )
        try:
            response_body = self._http_request(request)
            response_json = json.loads(response_body.decode("utf-8"))
            content = response_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LLMFacilityError("LLM_PROVIDER_ERROR", "chat completion response was not valid") from exc
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion content was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion JSON must be an object")
        usage = _provider_usage(response_json.get("usage"))
        if usage:
            parsed["__llm_usage"] = usage
        return parsed


def _validate_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != "sequential_reading":
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match sequential_reading")
    if not resolution.supports_json:
        raise LLMFacilityError("LLM_MODULE_CAPABILITY_MISSING", "sequential_reading requires a JSON-capable model")
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _sequential_reading_messages(
    *,
    context: AgentContext,
    segments: list[dict[str, Any]],
    segment_text_store: SegmentTextStore,
) -> list[dict[str, str]]:
    if not segments:
        raise LLMFacilityError("VALIDATION_FAILED", "segments are required for sequential_reading")
    segment_blocks = [_segment_prompt_block(segment, segment_text_store) for segment in segments]
    return [
        {
            "role": "system",
            "content": (
                "You are the MiroFish sequential reading module. Return one JSON object with a notes array. "
                "Each note must include segment_id, summary, and payload_jsonb with characters, organizations, "
                "relationships, plot_threads, world_rules, events, and consistency_notes arrays. "
                "Do not include prompt, raw full text, API keys, credentials, or provider metadata in the output."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "tenant_id": context.tenant_id,
                    "project_id": context.project_id,
                    "run_id": context.run_id,
                    "module_key": "sequential_reading",
                    "segments": segment_blocks,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
        },
    ]


def _segment_prompt_block(segment: dict[str, Any], segment_text_store: SegmentTextStore) -> dict[str, Any]:
    segment_id = _required_text(segment.get("segment_id"), "segment_id")
    segment_order = segment.get("segment_order")
    if not isinstance(segment_order, int) or segment_order < 0:
        raise LLMFacilityError("VALIDATION_FAILED", "segment_order must be a non-negative integer")
    object_key = _required_text(segment.get("object_key"), "object_key")
    try:
        text = segment_text_store.read_bytes(object_key).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LLMFacilityError("TEXT_SEGMENT_DECODE_FAILED", "segment text was not valid UTF-8") from exc
    except Exception as exc:
        raise LLMFacilityError("TEXT_SEGMENT_READ_FAILED", "segment text read failed") from exc
    return {
        "segment_id": segment_id,
        "segment_order": segment_order,
        "chapter_guess": _optional_text(segment.get("chapter_guess")),
        "title_guess": _optional_text(segment.get("title_guess")),
        "text": text,
    }


def _required_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMFacilityError("VALIDATION_FAILED", f"{field_name} is required")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise LLMFacilityError("VALIDATION_FAILED", "segment metadata must be text")
    return value


def _chat_request_body(resolution: ModuleBindingResolution, messages: list[dict[str, str]]) -> dict[str, Any]:
    body: dict[str, Any] = {
        "model": resolution.model_id,
        "messages": messages,
        "response_format": {"type": "json_object"},
    }
    temperature = _number_setting(resolution.settings, "temperature")
    if temperature is not None:
        body["temperature"] = temperature
    max_tokens = _number_setting(resolution.settings, "max_tokens")
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    return body


def _number_setting(settings: dict[str, Any], key: str) -> int | float | None:
    value = settings.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _provider_usage(value: Any) -> dict[str, int | float] | None:
    if not isinstance(value, dict):
        return None
    usage: dict[str, int | float] = {}
    prompt_tokens = _non_negative_int(value.get("prompt_tokens") or value.get("input_tokens"))
    completion_tokens = _non_negative_int(value.get("completion_tokens") or value.get("output_tokens"))
    total_tokens = _non_negative_int(value.get("total_tokens"))
    cost_estimate = _non_negative_number(value.get("cost_estimate") or value.get("cost"))
    if prompt_tokens is not None:
        usage["prompt_tokens"] = prompt_tokens
    if completion_tokens is not None:
        usage["completion_tokens"] = completion_tokens
    if total_tokens is not None:
        usage["total_tokens"] = total_tokens
    if cost_estimate is not None:
        usage["cost_estimate"] = cost_estimate
    return usage or None


def _non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value >= 0 and value.is_integer():
        return int(value)
    return None


def _non_negative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and value >= 0:
        return float(value)
    return None


def _chat_completions_url(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if normalized.endswith("/chat/completions"):
        return normalized
    return f"{normalized}/chat/completions"


def _failed(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "error": {
            "code": code,
            "message": message,
        },
        "module_key": "sequential_reading",
    }


def _row_value(row: Any, index: int, key: str) -> str:
    if isinstance(row, dict):
        value = row.get(key)
    else:
        value = row[index]
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    return value.strip()


def _row_bool(row: Any, index: int, key: str) -> bool:
    if isinstance(row, dict):
        value = row.get(key)
    else:
        value = row[index]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "t", "1", "yes"}
    return bool(value)


def _settings_from_row(row: Any, index: int, key: str) -> dict[str, Any]:
    if isinstance(row, dict):
        value = row.get(key)
    else:
        value = row[index]
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise LLMFacilityError("LLM_BINDING_QUERY_FAILED", "binding settings_jsonb was not valid JSON") from exc
        if isinstance(parsed, dict):
            return parsed
    raise LLMFacilityError("LLM_BINDING_QUERY_FAILED", "binding settings_jsonb must be an object")


def _parse_aes_256_key(key_material: str) -> bytes:
    trimmed = key_material.strip() if isinstance(key_material, str) else ""
    if not trimmed:
        raise LLMFacilityError("LLM_CREDENTIAL_KEY_UNCONFIGURED", "LLM credential encryption key is required")
    try:
        if len(trimmed) == 64 and all(char in "0123456789abcdefABCDEF" for char in trimmed):
            key = bytes.fromhex(trimmed)
        else:
            key = base64.b64decode(trimmed, validate=True)
    except ValueError as exc:
        raise LLMFacilityError("LLM_CREDENTIAL_KEY_INVALID", "expected 32-byte AES key material") from exc
    if len(key) != 32:
        raise LLMFacilityError("LLM_CREDENTIAL_KEY_INVALID", "expected 32-byte AES key material")
    return key


def _uuid_text_or_none(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return str(UUID(value.strip()))
    except ValueError:
        return None


def _parse_aes_gcm_envelope(envelope: str) -> tuple[str, str, bytes, bytes, bytes]:
    parts = envelope.split(":") if isinstance(envelope, str) else []
    if len(parts) != 5:
        raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "unsupported credential cipher")
    algorithm, version, iv_b64, tag_b64, ciphertext_b64 = parts
    try:
        iv = base64.b64decode(iv_b64, validate=True)
        auth_tag = base64.b64decode(tag_b64, validate=True)
        ciphertext = base64.b64decode(ciphertext_b64, validate=True)
    except ValueError as exc:
        raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "credential envelope was not valid base64") from exc
    if not iv or not auth_tag or not ciphertext:
        raise LLMFacilityError("LLM_CREDENTIAL_UNAVAILABLE", "credential envelope was incomplete")
    return algorithm, version, iv, auth_tag, ciphertext


def _urlopen_bytes(request: Request) -> bytes:
    with urlopen(request, timeout=60) as response:
        return response.read()
