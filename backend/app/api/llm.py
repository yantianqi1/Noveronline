"""LLM 设施面板 API。"""

import logging
import traceback

from flask import jsonify, request

from . import llm_bp
from ..config import Config
from ..services.llm_activity_tracker import llm_activity_tracker
from ..services.llm_concurrency_service import llm_concurrency_service as _concurrency_svc
from ..services.llm_settings_service import LlmSettingsService

logger = logging.getLogger(__name__)


def _service() -> LlmSettingsService:
    return LlmSettingsService()


def _require_admin():
    """Check Bearer token for mutation endpoints. Skip if ADMIN_SECRET is empty."""
    secret = Config.ADMIN_SECRET
    if not secret:
        return None
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {secret}":
        return None
    return jsonify({"success": False, "error": "未授权：需要有效的 ADMIN_SECRET"}), 401


def _error_response(error: Exception, status_code: int = 500):
    logger.error("LLM API error (status=%d): %s\n%s", status_code, error, traceback.format_exc())
    return (
        jsonify(
            {
                "success": False,
                "error": str(error),
            }
        ),
        status_code,
    )


@llm_bp.route("/settings", methods=["GET"])
def get_llm_settings():
    try:
        return jsonify({"success": True, "data": _service().get_snapshot()})
    except Exception as error:
        return _error_response(error)


@llm_bp.route("/channels", methods=["POST"])
def create_llm_channel():
    denied = _require_admin()
    if denied:
        return denied
    try:
        payload = request.get_json() or {}
        channel = _service().create_channel(payload)
        return jsonify({"success": True, "data": channel}), 201
    except ValueError as error:
        return _error_response(error, 400)
    except Exception as error:
        return _error_response(error)


@llm_bp.route("/channels/<channel_key>", methods=["PATCH"])
def update_llm_channel(channel_key: str):
    denied = _require_admin()
    if denied:
        return denied
    try:
        payload = request.get_json() or {}
        channel = _service().update_channel(channel_key, payload)
        return jsonify({"success": True, "data": channel})
    except ValueError as error:
        return _error_response(error, 400)
    except Exception as error:
        return _error_response(error)


@llm_bp.route("/channels/<channel_key>", methods=["DELETE"])
def delete_llm_channel(channel_key: str):
    denied = _require_admin()
    if denied:
        return denied
    try:
        result = _service().delete_channel(channel_key)
        return jsonify({"success": True, "data": result})
    except ValueError as error:
        return _error_response(error, 404)
    except Exception as error:
        return _error_response(error)


@llm_bp.route("/channels/<channel_key>/sync-models", methods=["POST"])
def sync_llm_channel_models(channel_key: str):
    denied = _require_admin()
    if denied:
        return denied
    try:
        channel = _service().sync_models(channel_key)
        return jsonify({"success": True, "data": channel})
    except ValueError as error:
        return _error_response(error, 400)
    except Exception as error:
        return _error_response(error, 500)


@llm_bp.route("/module-bindings/<module_key>", methods=["PUT"])
def update_llm_module_binding(module_key: str):
    denied = _require_admin()
    if denied:
        return denied
    try:
        payload = request.get_json() or {}
        binding = _service().set_module_binding(module_key, payload)
        return jsonify({"success": True, "data": binding})
    except ValueError as error:
        return _error_response(error, 400)
    except Exception as error:
        return _error_response(error)


@llm_bp.route("/module-bindings/<module_key>", methods=["DELETE"])
def delete_llm_module_binding(module_key: str):
    denied = _require_admin()
    if denied:
        return denied
    try:
        result = _service().delete_module_binding(module_key)
        return jsonify({"success": True, "data": result})
    except ValueError as error:
        return _error_response(error, 404)
    except Exception as error:
        return _error_response(error)


@llm_bp.route("/activity", methods=["GET"])
def get_llm_activity():
    """返回当前所有活跃 LLM 调用快照和各渠道并发状态。"""
    try:
        calls = llm_activity_tracker.snapshot()

        # 收集所有相关渠道的并发信息
        seen_channels = {c["channel_key"] for c in calls if c["channel_key"]}
        seen_channels.update(_concurrency_svc.channel_keys())

        channels = {}
        for ck in seen_channels:
            if ck:
                channels[ck] = _concurrency_svc.snapshot(ck)

        return jsonify({
            "success": True,
            "data": {
                "calls": calls,
                "channels": channels,
                "total_active": len(calls),
            },
        })
    except Exception as error:
        return _error_response(error)
