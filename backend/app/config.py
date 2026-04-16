"""
配置管理
统一从项目根目录 .env 加载配置。
"""

import os
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

project_root_env = os.path.join(os.path.dirname(__file__), "../../.env")
_DEFAULT_UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    load_dotenv(override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=project_root_env if os.path.exists(project_root_env) else None,
        extra="ignore",
    )

    SECRET_KEY: str | None = None
    DEBUG: bool = True
    JSON_AS_ASCII: bool = False

    DATABASE_URL: str = "sqlite:///./data/mirofish.db"
    LLM_REQUEST_TIMEOUT_SECONDS: float = 120
    LLM_FACILITY_DB_FILENAME: str = "llm_facility.sqlite3"
    ARCHIVE_LIBRARY_DB_FILENAME: str = "archive_library.sqlite3"
    ASSETS_GLOBAL_DB_FILENAME: str = "assets_library.sqlite3"
    ASSETS_PROJECT_DB_FILENAME: str = "project_assets.sqlite3"

    ZEP_API_KEY: str | None = None

    MAX_CONTENT_LENGTH: int = 100 * 1024 * 1024
    UPLOAD_FOLDER: str = _DEFAULT_UPLOAD_FOLDER
    ALLOWED_EXTENSIONS: set[str] = Field(
        default_factory=lambda: {"pdf", "md", "txt", "markdown"}
    )

    DEFAULT_CHUNK_SIZE: int = 800
    DEFAULT_CHUNK_OVERLAP: int = 120
    NARRATIVE_DEFAULT_BRANCH_COUNT: int = 1
    NARRATIVE_DEFAULT_TIMELINE_STEPS: int = 12
    ADMIN_SECRET: str = ""


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DEBUG = os.environ.get("APP_DEBUG", "true").lower() == "true"
    JSON_AS_ASCII = False

    LLM_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "120"))
    LLM_FACILITY_DB_FILENAME = "llm_facility.sqlite3"
    ARCHIVE_LIBRARY_DB_FILENAME = "archive_library.sqlite3"
    ASSETS_GLOBAL_DB_FILENAME = "assets_library.sqlite3"
    ASSETS_PROJECT_DB_FILENAME = "project_assets.sqlite3"

    ZEP_API_KEY = os.environ.get("ZEP_API_KEY")

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    UPLOAD_FOLDER = _DEFAULT_UPLOAD_FOLDER
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    DEFAULT_CHUNK_SIZE = 800
    DEFAULT_CHUNK_OVERLAP = 120

    NARRATIVE_DEFAULT_BRANCH_COUNT = int(os.environ.get("NARRATIVE_DEFAULT_BRANCH_COUNT", "1"))
    NARRATIVE_DEFAULT_TIMELINE_STEPS = int(os.environ.get("NARRATIVE_DEFAULT_TIMELINE_STEPS", "12"))

    ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")

    @classmethod
    def validate(cls):
        return []
