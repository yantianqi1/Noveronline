import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.main import app


def test_llm_contract_baseline_exposes_core_routes():
    paths = {route.path for route in app.routes if hasattr(route, "path")}

    assert "/api/v2/llm/settings" in paths
    assert "/api/v2/llm/channels" in paths
    assert "/api/v2/llm/channels/{channel_key}" in paths
    assert "/api/v2/llm/channels/{channel_key}/model-syncs" in paths
    assert "/api/v2/llm/module-bindings/{module_key}" in paths
    assert "/api/v2/llm/activity" in paths
