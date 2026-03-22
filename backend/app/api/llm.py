"""LLM 设施面板 API。"""

import traceback

from flask import jsonify, request

from . import llm_bp
from ..services.llm_settings_service import LlmSettingsService


def _service() -> LlmSettingsService:
    return LlmSettingsService()


def _error_response(error: Exception, status_code: int = 500):
    return (
        jsonify(
            {
                "success": False,
                "error": str(error),
                "traceback": traceback.format_exc(),
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
    try:
        result = _service().delete_channel(channel_key)
        return jsonify({"success": True, "data": result})
    except ValueError as error:
        return _error_response(error, 404)
    except Exception as error:
        return _error_response(error)


@llm_bp.route("/channels/<channel_key>/sync-models", methods=["POST"])
def sync_llm_channel_models(channel_key: str):
    try:
        channel = _service().sync_models(channel_key)
        return jsonify({"success": True, "data": channel})
    except ValueError as error:
        return _error_response(error, 400)
    except Exception as error:
        return _error_response(error, 500)


@llm_bp.route("/module-bindings/<module_key>", methods=["PUT"])
def update_llm_module_binding(module_key: str):
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
    try:
        result = _service().delete_module_binding(module_key)
        return jsonify({"success": True, "data": result})
    except ValueError as error:
        return _error_response(error, 404)
    except Exception as error:
        return _error_response(error)
