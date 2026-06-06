import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import app


def test_worldline_contract_baseline_exposes_core_routes():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    expected = {
        "/api/v2/worldlines/preparations",
        "/api/v2/worldlines/preparations/{preparation_id}",
        "/api/v2/worldlines/preparations/{preparation_id}/agents",
        "/api/v2/worldlines/preparations/{preparation_id}/start",
        "/api/v2/worldlines/sessions",
        "/api/v2/worldlines/sessions/{session_id}",
        "/api/v2/worldlines/sessions/{session_id}/timeline",
        "/api/v2/worldlines/sessions/{session_id}/commands/advance",
        "/api/v2/worldlines/sessions/{session_id}/commands/inject-variable",
        "/api/v2/worldlines/sessions/{session_id}/commands/agent-actions",
        "/api/v2/worldlines/sessions/{session_id}/commands/agent-dialogues",
        "/api/v2/worldlines/sessions/{session_id}/agents/{agent_id}",
        "/api/v2/worldlines/sessions/{session_id}/agent-history",
        "/api/v2/worldlines/sessions/{session_id}/agent-actions",
        "/api/v2/worldlines/sessions/{session_id}/agent-memory",
        "/api/v2/worldlines/sessions/{session_id}/agent-memory-context",
        "/api/v2/worldlines/sessions/{session_id}/agent-dialogues",
        "/api/v2/worldlines/sessions/{session_id}/relations",
        "/api/v2/worldlines/sessions/{session_id}/event-adoptions",
        "/api/v2/worldlines/sessions/{session_id}/events/{event_id}",
        "/api/v2/worldlines/sessions/{session_id}/events",
        "/api/v2/worldlines/sessions/{session_id}/auto-evolutions",
        "/api/v2/worldlines/sessions/{session_id}/auto-evolutions/{auto_evolution_id}/events",
    }

    assert expected.issubset(paths)
