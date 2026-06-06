import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import app


def test_workspace_contract_baseline_exposes_core_routes():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v2/workspaces" in paths
    assert "/api/v2/workspaces/{workspace_id}" in paths
    assert "/api/v2/workspaces/{workspace_id}/ingests" in paths
