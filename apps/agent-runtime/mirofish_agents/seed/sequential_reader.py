from __future__ import annotations

import base64
import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol
from urllib.request import Request, urlopen
from uuid import UUID

from mirofish_agents.common.context import AgentContext
from mirofish_agents.llm.model_capabilities import effective_supports_json

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
_TRANSIENT_BATCH_CODES = frozenset(
    {
        "SCHEMA_VALIDATION_FAILED",
        "LLM_PROVIDER_ERROR",
        "LLM_PROVIDER_TIMEOUT",
        "LLM_PROVIDER_RATE_LIMITED",
    }
)


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
                          AND m.enabled = TRUE
                         WHERE b.tenant_id::text = i.tenant_id
                           AND (b.project_id::text = i.project_id OR b.project_id IS NULL)
                           AND b.module_key = i.module_key
                         UNION ALL
                         SELECT
                           i.tenant_id::uuid AS tenant_id,
                           NULL::uuid AS project_id,
                           d.module_key,
                           d.channel_id,
                           d.model_id,
                           c.provider,
                           c.base_url,
                           COALESCE(m.supports_json, false) AS supports_json,
                           d.settings_jsonb,
                           2 AS binding_rank
                         FROM llm_platform_module_defaults d
                         JOIN input i
                           ON i.module_key = d.module_key
                         JOIN llm_channels c
                           ON c.channel_id = d.channel_id
                          AND c.enabled = TRUE
                          AND c.tenant_id IS NULL
                         JOIN llm_models m
                           ON m.channel_id = d.channel_id
                          AND m.model_id = d.model_id
                          AND m.tenant_id IS NULL
                          AND m.enabled = TRUE
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
        model_id = _row_value(row, 4, "model_id")
        stored_supports_json = _row_bool(row, 7, "supports_json")
        # Catalog default FALSE blocked real DeepSeek/GPT chat models. OR in
        # inferred chat capabilities so sequential reading can call the provider.
        return ModuleBindingResolution(
            tenant_id=_row_value(row, 0, "tenant_id"),
            project_id=_row_value(row, 1, "project_id") or None,
            module_key=_row_value(row, 2, "module_key"),
            channel_id=_row_value(row, 3, "channel_id"),
            model_id=model_id,
            provider=_row_value(row, 5, "provider"),
            base_url=_row_value(row, 6, "base_url"),
            credential_ref=_row_value(row, 3, "channel_id"),
            supports_json=effective_supports_json(model_id=model_id, stored=stored_supports_json),
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
        progress_callback: Callable[..., None] | None = None,
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
            # Long novels produce hundreds of segments. One giant provider call
            # exhausts context/quota and fails permanently on retry. Batch by text size.
            batches = _segment_batches(
                segments,
                segment_text_store=self._segment_text_store,
                settings=resolution.settings,
            )
            total_segments = len(segments)
            completed_segments = 0
            notes: list[Any] = []
            for batch_index, batch in enumerate(batches):
                _emit_sequential_progress(
                    progress_callback,
                    phase="batch_start",
                    batch_index=batch_index,
                    batch_count=len(batches),
                    batch=batch,
                    completed_segments=completed_segments,
                    total_segments=total_segments,
                )
                try:
                    batch_notes = _read_batch_with_recovery(
                        chat_client=self._chat_client,
                        context=context,
                        resolution=resolution,
                        api_key=api_key.strip(),
                        batch=batch,
                        segment_text_store=self._segment_text_store,
                        progress_callback=progress_callback,
                        batch_index=batch_index,
                        batch_count=len(batches),
                        completed_segments=completed_segments,
                        total_segments=total_segments,
                    )
                    notes.extend(batch_notes)
                    completed_segments += len(batch)
                    _emit_sequential_progress(
                        progress_callback,
                        phase="batch_completed",
                        batch_index=batch_index,
                        batch_count=len(batches),
                        batch=batch,
                        completed_segments=completed_segments,
                        total_segments=total_segments,
                        note_count=len(batch_notes),
                    )
                except LLMFacilityError as exc:
                    _emit_sequential_progress(
                        progress_callback,
                        phase="batch_failed",
                        batch_index=batch_index,
                        batch_count=len(batches),
                        batch=batch,
                        completed_segments=completed_segments,
                        total_segments=total_segments,
                        error_code=exc.code,
                        error_message=exc.message,
                    )
                    raise
        except LLMFacilityError as exc:
            return _failed(exc.code, exc.message)
        except Exception as exc:
            return _failed("LLM_PROVIDER_ERROR", str(exc))

        return {
            "status": "completed",
            "pass_id": _reading_pass_id(context),
            "module_key": module_key,
            "model_id": resolution.model_id,
            "notes": notes,
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
        parsed = _parse_chat_json_content(content)
        usage = _provider_usage(response_json.get("usage"))
        if usage:
            parsed["__llm_usage"] = usage
        return parsed


def _validate_resolution(resolution: ModuleBindingResolution) -> None:
    if resolution.module_key != "sequential_reading":
        raise LLMFacilityError("LLM_MODULE_UNBOUND", "resolved module key does not match sequential_reading")
    supports_json = resolution.supports_json or effective_supports_json(
        model_id=resolution.model_id,
        stored=False,
    )
    if not supports_json:
        raise LLMFacilityError("LLM_MODULE_CAPABILITY_MISSING", "sequential_reading requires a JSON-capable model")
    for field_name in ("channel_id", "model_id", "provider", "base_url", "credential_ref"):
        value = getattr(resolution, field_name)
        if not isinstance(value, str) or not value.strip():
            raise LLMFacilityError("LLM_PROVIDER_ERROR", f"resolved LLM module is missing {field_name}")


def _read_batch_with_recovery(
    *,
    chat_client: JSONChatClient,
    context: AgentContext,
    resolution: ModuleBindingResolution,
    api_key: str,
    batch: list[dict[str, Any]],
    segment_text_store: SegmentTextStore,
    progress_callback: Callable[..., None] | None,
    batch_index: int,
    batch_count: int,
    completed_segments: int,
    total_segments: int,
    attempt: int = 0,
) -> list[Any]:
    """Read one batch; on JSON/provider flakiness retry once, then split the batch."""
    try:
        messages = _sequential_reading_messages(
            context=context,
            segments=batch,
            segment_text_store=segment_text_store,
        )
        response_json = chat_client.complete_json(
            context=context,
            resolution=resolution,
            api_key=api_key,
            messages=messages,
        )
        batch_notes = response_json.get("notes", [])
        if not isinstance(batch_notes, list):
            raise LLMFacilityError(
                "SCHEMA_VALIDATION_FAILED",
                "sequential reading notes must be an array",
            )
        return batch_notes
    except LLMFacilityError as exc:
        if exc.code not in _TRANSIENT_BATCH_CODES:
            raise
        # One more attempt on the same batch before splitting.
        if attempt == 0:
            _emit_sequential_progress(
                progress_callback,
                phase="batch_retry",
                batch_index=batch_index,
                batch_count=batch_count,
                batch=batch,
                completed_segments=completed_segments,
                total_segments=total_segments,
                error_code=exc.code,
                error_message=exc.message,
            )
            return _read_batch_with_recovery(
                chat_client=chat_client,
                context=context,
                resolution=resolution,
                api_key=api_key,
                batch=batch,
                segment_text_store=segment_text_store,
                progress_callback=progress_callback,
                batch_index=batch_index,
                batch_count=batch_count,
                completed_segments=completed_segments,
                total_segments=total_segments,
                attempt=1,
            )
        # Multi-segment batch: split and recover progress instead of failing the whole novel.
        if len(batch) > 1:
            mid = max(1, len(batch) // 2)
            left = batch[:mid]
            right = batch[mid:]
            _emit_sequential_progress(
                progress_callback,
                phase="batch_split",
                batch_index=batch_index,
                batch_count=batch_count,
                batch=batch,
                completed_segments=completed_segments,
                total_segments=total_segments,
                error_code=exc.code,
                error_message=exc.message,
            )
            left_notes = _read_batch_with_recovery(
                chat_client=chat_client,
                context=context,
                resolution=resolution,
                api_key=api_key,
                batch=left,
                segment_text_store=segment_text_store,
                progress_callback=progress_callback,
                batch_index=batch_index,
                batch_count=batch_count,
                completed_segments=completed_segments,
                total_segments=total_segments,
                attempt=0,
            )
            right_notes = _read_batch_with_recovery(
                chat_client=chat_client,
                context=context,
                resolution=resolution,
                api_key=api_key,
                batch=right,
                segment_text_store=segment_text_store,
                progress_callback=progress_callback,
                batch_index=batch_index,
                batch_count=batch_count,
                completed_segments=completed_segments + len(left),
                total_segments=total_segments,
                attempt=0,
            )
            return [*left_notes, *right_notes]
        raise


def _parse_chat_json_content(content: Any) -> dict[str, Any]:
    """Parse model content into a JSON object, tolerating common markdown fences."""
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion content was not valid JSON")
    text = content.strip()
    if not text:
        raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion content was not valid JSON")
    candidates = [text]
    fence = _JSON_FENCE_RE.search(text)
    if fence:
        candidates.append(fence.group(1).strip())
    # Leading/trailing prose around a top-level object.
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise LLMFacilityError("SCHEMA_VALIDATION_FAILED", "chat completion content was not valid JSON")


def _emit_sequential_progress(
    progress_callback: Callable[..., None] | None,
    *,
    phase: str,
    batch_index: int,
    batch_count: int,
    batch: list[dict[str, Any]],
    completed_segments: int,
    total_segments: int,
    note_count: int | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Best-effort Overview progress hook; never fail the reader on callback errors."""
    if progress_callback is None:
        return
    first = batch[0] if batch else {}
    last = batch[-1] if batch else {}
    segment_order_start = first.get("segment_order") if isinstance(first, dict) else None
    segment_order_end = last.get("segment_order") if isinstance(last, dict) else None
    chapter_guess = _optional_text_safe(first.get("chapter_guess") if isinstance(first, dict) else None)
    title_guess = _optional_text_safe(first.get("title_guess") if isinstance(first, dict) else None)
    label = title_guess or chapter_guess or (
        f"段落 {segment_order_start}" if isinstance(segment_order_start, int) else f"批次 {batch_index + 1}"
    )
    if phase == "batch_start":
        message = f"开始精读 {completed_segments + 1}-{min(completed_segments + len(batch), total_segments)}/{total_segments} · {label}"
        status = "running"
    elif phase == "batch_completed":
        message = f"完成精读 {completed_segments}/{total_segments} · {label}"
        status = "completed"
    elif phase == "batch_retry":
        message = f"重试精读 {completed_segments + 1}-{min(completed_segments + len(batch), total_segments)}/{total_segments} · {label}"
        status = "running"
    elif phase == "batch_split":
        message = f"拆分重试 {completed_segments + 1}-{min(completed_segments + len(batch), total_segments)}/{total_segments} · {label}"
        status = "running"
    else:
        message = f"精读失败 {completed_segments}/{total_segments} · {label}"
        status = "failed"
    payload: dict[str, Any] = {
        "stage": "sequential_reading",
        "status": status,
        "phase": phase,
        "message": message,
        "batch_index": batch_index,
        "batch_count": batch_count,
        "completed_segments": completed_segments,
        "total_segments": total_segments,
        "segment_order_start": segment_order_start if isinstance(segment_order_start, int) else None,
        "segment_order_end": segment_order_end if isinstance(segment_order_end, int) else None,
    }
    if chapter_guess:
        payload["chapter_guess"] = chapter_guess
    if title_guess:
        payload["title_guess"] = title_guess
    if note_count is not None:
        payload["note_count"] = note_count
    if error_code:
        payload["error_code"] = error_code
    if error_message:
        # Public log line only — keep short and free of raw content.
        payload["error_message"] = error_message[:180]
    try:
        progress_callback(payload)
    except Exception:
        return


def _optional_text_safe(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    # Overview log labels only; never ship long excerpt text.
    return trimmed[:80]


# Sequential-reading batch sizing. Modern long-context models comfortably read
# tens of thousands of tokens at once, so batch by ESTIMATED TOKENS (not raw
# chars) with a generous default. Chinese text runs ~1.5 tokens per character;
# other scripts ~0.25 per character, so the estimator walks characters rather
# than trusting a single chars-per-token ratio.
DEFAULT_BATCH_MAX_TOKENS = 60_000
# Output budget for a full batch's structured notes. Must comfortably exceed the
# largest batch's note JSON, or the provider truncates mid-JSON and the read fails.
DEFAULT_MAX_OUTPUT_TOKENS = 30_000
_TOKENS_PER_WIDE_CHAR = 1.5
_TOKENS_PER_NARROW_CHAR = 0.25


def _estimate_tokens(text: str) -> int:
    tokens = 0.0
    for ch in text:
        tokens += _TOKENS_PER_WIDE_CHAR if ord(ch) > 0xFF else _TOKENS_PER_NARROW_CHAR
    return max(1, int(tokens) + 1)


def _segment_batches(
    segments: list[dict[str, Any]],
    *,
    segment_text_store: SegmentTextStore,
    settings: dict[str, Any],
) -> list[list[dict[str, Any]]]:
    if not segments:
        raise LLMFacilityError("VALIDATION_FAILED", "segments are required for sequential_reading")
    max_segments = _positive_int_setting(settings, "batch_max_segments", default=48)
    max_tokens = _positive_int_setting(settings, "batch_max_tokens", default=DEFAULT_BATCH_MAX_TOKENS)
    # Legacy char-based cap still honoured when explicitly configured, but no
    # longer defaults (token budget supersedes it).
    legacy_max_chars = settings.get("batch_max_chars")
    max_chars = legacy_max_chars if isinstance(legacy_max_chars, int) and not isinstance(legacy_max_chars, bool) and legacy_max_chars > 0 else None

    # Measure every segment once (tokens for budget, chars for the legacy cap).
    measured: list[tuple[dict[str, Any], int, int, str | None]] = []
    for segment in segments:
        object_key = _required_text(segment.get("object_key"), "object_key")
        try:
            text = segment_text_store.read_bytes(object_key).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise LLMFacilityError("TEXT_SEGMENT_DECODE_FAILED", "segment text was not valid UTF-8") from exc
        except Exception as exc:
            raise LLMFacilityError("TEXT_SEGMENT_READ_FAILED", "segment text read failed") from exc
        chapter = segment.get("chapter_guess") if isinstance(segment.get("chapter_guess"), str) else None
        measured.append((segment, _estimate_tokens(text), len(text), chapter))

    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_tokens = 0
    current_chars = 0
    current_chapter: str | None = None

    def flush() -> None:
        nonlocal current, current_tokens, current_chars, current_chapter
        if current:
            batches.append(current)
        current = []
        current_tokens = 0
        current_chars = 0
        current_chapter = None

    def add(segment: dict[str, Any], tokens: int, chars: int, chapter: str | None) -> None:
        nonlocal current_tokens, current_chars, current_chapter
        current.append(segment)
        current_tokens += tokens
        current_chars += chars
        current_chapter = chapter if chapter is not None else current_chapter

    def fits(tokens: int, chars: int, count: int = 1) -> bool:
        # Whether adding `count` segments of `tokens`/`chars` to the CURRENT batch
        # keeps it within all limits (per-batch segment count, tokens, chars). An
        # empty batch only "fits" a group if that group alone is within the budget,
        # so an oversized chapter is never silently kept whole.
        if len(current) + count > max_segments:
            return False
        if current_tokens + tokens > max_tokens:
            return False
        if max_chars is not None and current_chars + chars > max_chars:
            return False
        return True

    # Group consecutive segments into chapters (None chapter_guess attaches to the
    # previous chapter / forms its own group), then greedily pack WHOLE chapters
    # into each batch up to the token budget. A chapter is never split across two
    # LLM calls — but short chapters pack many-per-batch instead of one-per-batch.
    groups: list[tuple[str | None, list[tuple[dict[str, Any], int, int]]]] = []
    for segment, tokens, chars, chapter in measured:
        if groups and (chapter is None or chapter == groups[-1][0]):
            groups[-1][1].append((segment, tokens, chars))
        else:
            groups.append((chapter, [(segment, tokens, chars)]))

    for chapter, group_segs in groups:
        group_tokens = sum(tokens for _, tokens, _ in group_segs)
        group_chars = sum(chars for _, _, chars in group_segs)

        if fits(group_tokens, group_chars, len(group_segs)):
            # Whole chapter fits in the current batch — keep it together.
            for segment, tokens, chars in group_segs:
                add(segment, tokens, chars, chapter)
            continue

        # Whole chapter does not fit here. Start a fresh batch for it — but only
        # if it actually fits an empty batch under ALL limits (count included).
        flush()
        if len(group_segs) <= max_segments and group_tokens <= max_tokens and (max_chars is None or group_chars <= max_chars):
            # The chapter fits in an empty batch on its own.
            for segment, tokens, chars in group_segs:
                add(segment, tokens, chars, chapter)
            flush()
            continue

        # A single chapter exceeds the whole budget: fall back to packing its
        # segments individually (never splitting a segment mid-way), honouring
        # the same per-batch count/token/char limits as the chapter path.
        for segment, tokens, chars in group_segs:
            if current and not fits(tokens, chars):
                flush()
            add(segment, tokens, chars, chapter)
            if len(current) >= max_segments or current_tokens >= max_tokens or (max_chars is not None and current_chars >= max_chars):
                flush()

    flush()
    return batches


def _positive_int_setting(settings: dict[str, Any], key: str, *, default: int) -> int:
    value = settings.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return default
    return value


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
                "Each character or organization must be an object with name, a short one-line state_summary, "
                "and a description: a detailed 2-4 sentence Chinese profile covering identity, temperament, "
                "motivation, and relation to the main plot. Do not collapse description into a one-line gloss. "
                "The extracted facts become story assets that a writer recalls while drafting, so every "
                "world_rules, relationships, and plot_threads entry is a writer-facing record, never a raw "
                "quote or fragment of the source text. "
                "Each world_rules entry must be an object with: title, a short Chinese noun phrase naming the "
                "rule itself (at most 12 characters, e.g. \"武夫修炼要求\", \"连坐制度\", never a full sentence); "
                "summary, one complete Chinese sentence stating the rule; detail, a detailed 2-4 sentence "
                "Chinese body explaining scope, preconditions, exceptions, and story consequences so a writer "
                "can apply the rule while drafting; optional category, confidence, and evidence, a short "
                "verbatim quote supporting the rule. Never copy the same sentence into title, summary, and "
                "detail. "
                "Each relationships entry must be an object with source and target entity names; type, a short "
                "Chinese relationship label such as \"师徒\", \"上下级\", \"敌对\", \"家人\" (never English snake_case, "
                "never a sentence); summary, one complete Chinese sentence describing how the two parties "
                "relate right now; description, a detailed 2-4 sentence Chinese account of how the "
                "relationship formed, its current state, tension, and direction of change so a writer can "
                "write the pair's scenes; optional evidence. "
                "Each plot_threads entry must be an object with title, a short Chinese phrase naming the "
                "thread (at most 12 characters); summary, one complete Chinese sentence stating where the "
                "thread stands; optional status; description, a detailed 2-4 sentence Chinese account of the "
                "thread's setup, current development, and open hooks; optional evidence. "
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
    # Large token-batched reads (default 60k input tokens) produce large JSON
    # outputs. Without an explicit max_tokens the provider caps output far below
    # what a full batch needs and the JSON gets truncated -> SCHEMA_VALIDATION_FAILED.
    # Default to a generous output budget; a module setting always overrides.
    max_tokens = _number_setting(resolution.settings, "max_tokens")
    if max_tokens is None:
        max_tokens = DEFAULT_MAX_OUTPUT_TOKENS
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


def _reading_pass_id(context: AgentContext) -> str:
    stable_key = ":".join(
        [
            "mirofish",
            "seed-sequential-reading-pass",
            context.tenant_id,
            context.project_id or "",
            context.run_id,
        ]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))


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
