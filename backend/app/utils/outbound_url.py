"""Outbound URL policy for legacy provider integrations."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit


def allowed_base_url_hosts(raw_hosts: str | None) -> frozenset[str]:
    return frozenset(
        item.strip().lower().rstrip(".")
        for item in str(raw_hosts or "").split(",")
        if item.strip()
    )


def validate_base_url(base_url: str, *, allowed_hosts: str | None) -> str:
    """Validate an OpenAI-compatible provider URL before any network request."""
    value = str(base_url or "").strip()
    parsed = urlsplit(value)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname:
        raise ValueError("base_url 必须使用 HTTPS 且包含主机名")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base_url 不得包含用户信息、查询参数或 fragment")
    if parsed.port not in (None, 443):
        raise ValueError("base_url 仅允许 HTTPS 默认端口")
    if hostname in {"localhost", "localhost.localdomain", "metadata.google.internal"}:
        raise ValueError("base_url 不允许访问本地主机或云元数据服务")
    if hostname.endswith((".local", ".internal")):
        raise ValueError("base_url 不允许访问内部域名")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ValueError("base_url 不允许访问私有或保留 IP 地址")
    hosts = allowed_base_url_hosts(allowed_hosts)
    if not hosts or hostname not in hosts:
        raise ValueError("base_url 主机不在允许的 provider 白名单中")
    return value.rstrip("/")
