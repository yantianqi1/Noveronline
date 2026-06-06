import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import app


def test_operation_contract_baseline_exposes_query_event_and_stream_routes():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v2/operations/{operation_id}" in paths
    assert "/api/v2/operations/{operation_id}/steps/{step_id}" in paths
    assert "/api/v2/operations/{operation_id}/events" in paths
    assert "/api/v2/operations/{operation_id}/stream" in paths
