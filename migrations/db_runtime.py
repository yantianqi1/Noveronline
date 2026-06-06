from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import Engine, create_engine


def load_metadata():
    api_root = Path(__file__).resolve().parents[1] / "apps" / "api"
    api_root_text = str(api_root)
    if api_root_text not in sys.path:
        sys.path.insert(0, api_root_text)
    from src.shared.db.base import metadata  # noqa: WPS433

    return metadata


def build_engine(database_url: str) -> Engine:
    return create_engine(database_url)
