"""Helpers for recording LLM calls into seed step traces."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


def append_llm_trace_call(
    step_ctx: Any,
    *,
    messages: Optional[List[Dict[str, str]]],
    response_text: str,
    error: Optional[str],
    started_at: float,
    call_type: str,
    model: str,
    module_key: str,
    module_label: str,
    channel_key: str,
    usage: Optional[Dict[str, int]] = None,
) -> None:
    """Append one concrete LLM call record to the active step trace."""
    step_ctx.calls.append(
        build_llm_trace_call(
            messages=messages,
            response_text=response_text,
            error=error,
            started_at=started_at,
            call_type=call_type,
            model=model,
            module_key=module_key,
            module_label=module_label,
            channel_key=channel_key,
            usage=usage,
        )
    )


def build_llm_trace_call(
    *,
    messages: Optional[List[Dict[str, str]]],
    response_text: str,
    error: Optional[str],
    started_at: float,
    call_type: str,
    model: str,
    module_key: str,
    module_label: str,
    channel_key: str,
    usage: Optional[Dict[str, int]],
) -> Dict[str, Any]:
    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    payload: Dict[str, Any] = {
        "call_id": f"call_{uuid.uuid4().hex[:12]}",
        "call_type": call_type,
        "module_key": module_key,
        "module_label": module_label or module_key,
        "model": model,
        "channel_key": channel_key,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "elapsed_ms": max(0, elapsed_ms),
        "messages": messages or [],
        "response_text": response_text or "",
        "error": error or "",
    }
    if usage is not None:
        payload["usage"] = usage
    return payload
