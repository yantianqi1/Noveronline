import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import app


def test_writer_contract_baseline_exposes_core_routes():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v2/chapter-context/options" in paths
    assert "/api/v2/chapter-context/builds" in paths
    assert "/api/v2/drafts" in paths
    assert "/api/v2/drafts/{draft_id}/revisions" in paths
    assert "/api/v2/drafts/{draft_id}/finalizations" in paths
    assert "/api/v2/workspaces/{workspace_id}/reviewer-rules" in paths
