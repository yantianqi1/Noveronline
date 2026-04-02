"""格式化上游服务错误，避免把整页 HTML 直接暴露给前端。"""

from __future__ import annotations

import html
import re
from typing import Any, Optional


HTML_MARKERS = ("<!doctype html", "<html")
TITLE_PATTERN = re.compile(r"<title>(.*?)</title>", re.IGNORECASE | re.DOTALL)
API_HOST_PATTERN = re.compile(r"\bapi\.[a-z0-9.-]+\b", re.IGNORECASE)
GENERIC_HOST_PATTERN = re.compile(r"\b[a-z0-9][a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE)
STATUS_PATTERN = re.compile(r"\b([45]\d{2})\b")
TAG_PATTERN = re.compile(r"<[^>]+>")


def format_upstream_service_error(exc: Exception, service_label: str = "上游 LLM 服务") -> str:
    html_body = _extract_html_body(exc)
    if not html_body:
        return str(exc)
    status_code = _extract_status_code(exc, html_body)
    host = _extract_host(html_body)
    return _format_html_error(service_label, status_code, host, html_body)


def _extract_html_body(exc: Exception) -> Optional[str]:
    for candidate in _candidate_texts(exc):
        if _looks_like_html(candidate):
            return candidate
    return None


def _candidate_texts(exc: Exception) -> list[str]:
    values = [str(exc)]
    body = getattr(exc, "body", None)
    if isinstance(body, str):
        values.append(body)
    response = getattr(exc, "response", None)
    response_text = getattr(response, "text", None)
    if isinstance(response_text, str):
        values.append(response_text)
    return values


def _looks_like_html(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in HTML_MARKERS)


def _extract_status_code(exc: Exception, html_body: str) -> Optional[int]:
    status_code = getattr(exc, "status_code", None)
    response = getattr(exc, "response", None)
    if status_code is None:
        status_code = getattr(response, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    match = STATUS_PATTERN.search(html_body)
    return int(match.group(1)) if match else None


def _extract_host(html_body: str) -> str:
    api_host_match = API_HOST_PATTERN.search(html_body)
    if api_host_match:
        return api_host_match.group(0)
    host_match = GENERIC_HOST_PATTERN.search(html_body)
    return host_match.group(0) if host_match else ""


def _format_html_error(
    service_label: str,
    status_code: Optional[int],
    host: str,
    html_body: str,
) -> str:
    title = _extract_title(html_body)
    status_label = _status_label(status_code, title)
    details = [status_label] if status_label else []
    if host:
        details.append(f"host={host}")
    detail_text = f"（{'，'.join(details)}）" if details else ""
    return f"{service_label}{detail_text}。源站返回了 HTML 错误页，未返回可解析的模型结果。"


def _extract_title(html_body: str) -> str:
    match = TITLE_PATTERN.search(html_body)
    if not match:
        return ""
    plain = TAG_PATTERN.sub("", match.group(1))
    return html.unescape(plain).strip()


def _status_label(status_code: Optional[int], title: str) -> str:
    if status_code == 504:
        return "HTTP 504 Gateway time-out"
    if isinstance(status_code, int):
        return f"HTTP {status_code}"
    return title
