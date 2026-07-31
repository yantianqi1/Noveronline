from __future__ import annotations

import os
from typing import BinaryIO


def response_limit_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default)).strip()
    try:
        limit = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if limit <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return limit


def read_response_limited(response: BinaryIO, *, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise ValueError("response byte limit must be positive")
    chunks: list[bytes] = []
    total = 0
    while total < max_bytes:
        chunk = response.read(min(64 * 1024, max_bytes - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("HTTP response exceeded the configured byte limit")
        chunks.append(chunk)
    return b"".join(chunks)
