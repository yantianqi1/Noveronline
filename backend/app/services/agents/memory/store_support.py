"""Agent 记忆存储共享支持函数。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict


def now_iso() -> str:
    return datetime.now().isoformat()


def memory_row(row, scope: str) -> Dict[str, Any]:
    payload = dict(row)
    payload["scope"] = scope
    payload["salience"] = float(payload.get("salience") or 0.0)
    payload["detail"] = json.loads(payload.get("detail_json") or "{}")
    payload["evidence"] = json.loads(payload.get("evidence_json") or "[]")
    payload["memory_layer"] = payload.get("memory_layer") or "canon"
    payload["status"] = payload.get("status") or "active"
    payload["version"] = int(payload.get("version") or 1)
    return payload


def event_row(row) -> Dict[str, Any]:
    payload = dict(row)
    payload["version"] = int(payload.get("version") or 1)
    payload["evidence"] = json.loads(payload.get("evidence_json") or "[]")
    return payload

