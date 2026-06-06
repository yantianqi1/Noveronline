import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import app


def test_archive_contract_baseline_exposes_core_routes():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v2/archives" in paths
    assert "/api/v2/archives/{archive_id}" in paths
    assert "/api/v2/archives/{archive_id}/memories" in paths
    assert "/api/v2/archives/{archive_id}/memory-events" in paths
    assert "/api/v2/archives/{archive_id}/memory-adoptions" in paths
    assert "/api/v2/archives/{archive_id}/memory-rejections" in paths
    assert "/api/v2/archive-maintenance/reindex" in paths
