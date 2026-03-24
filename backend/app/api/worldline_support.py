"""
世界线 API 公共依赖
"""

from flask import jsonify

from . import worldline_bp
from ..config import Config
from ..services.character_agent_service import CharacterAgentService
from ..services.world_state_store import WorldStateStore
from ..services.worldline_engine_factory import build_worldline_engine
from ..services.worldline_single_world import MAIN_WORLD_BRANCH_ID, current_world, resolve_branch_id

worldline_store = WorldStateStore()
character_agent_service = CharacterAgentService()


class _AttributeProxy:
    def __init__(self, resolver):
        self._resolver = resolver

    def __getattr__(self, name):
        return getattr(self._resolver(), name)


class _WorldlineEngineProxy:
    def __init__(self, store: WorldStateStore):
        self._store = store
        self._engine = None
        self._upload_folder = None

    def _resolve(self):
        current_upload_folder = Config.UPLOAD_FOLDER
        if self._engine is None or self._upload_folder != current_upload_folder:
            self._engine = build_worldline_engine(self._store)
            self._upload_folder = current_upload_folder
        return self._engine

    def __getattr__(self, name):
        return getattr(self._resolve(), name)


worldline_engine = _WorldlineEngineProxy(worldline_store)
worldline_runtime_service = _AttributeProxy(lambda: worldline_engine.runtime_service)
worldline_agent_registry = _AttributeProxy(lambda: worldline_runtime_service.registry)
worldline_memory_service = _AttributeProxy(lambda: worldline_engine.memory_service)


def ok(data):
    return jsonify({"success": True, "data": data})


def error(message: str, status: int = 400):
    return jsonify({"success": False, "error": message}), status


def project_graph_from_request(data):
    return data.get("project_id"), data.get("graph_id")


def requested_branch_id(data):
    return resolve_branch_id(data.get("branch_id"))


def current_world_payload(session):
    world = current_world(session)
    payload = world.to_dict()
    payload["branch_id"] = MAIN_WORLD_BRANCH_ID
    payload["title"] = world.title or "当前世界"
    payload["timeline_size"] = len(world.timeline)
    payload["pending_variable_count"] = len(world.pending_variables)
    payload["pending_action_count"] = len(world.pending_actions)
    payload["latest_event"] = world.timeline[-1].to_dict() if world.timeline else None
    return payload
