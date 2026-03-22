"""
世界线 API 公共依赖
"""

from flask import jsonify

from . import worldline_bp
from ..services.character_agent_service import CharacterAgentService
from ..services.world_state_store import WorldStateStore
from ..services.worldline_engine_factory import build_worldline_engine

worldline_store = WorldStateStore()
worldline_engine = build_worldline_engine(worldline_store)
character_agent_service = CharacterAgentService()
worldline_runtime_service = worldline_engine.runtime_service
worldline_agent_registry = worldline_runtime_service.registry


def ok(data):
    return jsonify({"success": True, "data": data})


def error(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def project_graph_from_request(data):
    return data.get("project_id"), data.get("graph_id")
