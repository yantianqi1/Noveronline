import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.bootstrap.settings import (
    AppSettings,
    DbSettings,
    LlmFacilitySettings,
    ObjectStorageSettings,
)


def test_bootstrap_settings_expose_split_runtime_groups():
    app = AppSettings()
    db = DbSettings()
    storage = ObjectStorageSettings()
    llm = LlmFacilitySettings()

    assert app.api_prefix == "/api/v2"
    assert db.host == "127.0.0.1"
    assert db.database == "mirofish"
    assert db.sqlalchemy_dsn.startswith("postgresql+psycopg://")
    assert storage.bucket == "mirofish-artifacts"
    assert storage.endpoint == "127.0.0.1:9000"
    assert llm.default_timeout_seconds == 60
    assert llm.activity_buffer_size == 200
