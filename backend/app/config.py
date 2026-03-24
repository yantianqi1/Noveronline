"""
配置管理
统一从项目根目录 .env 加载配置。
"""

import os
from dotenv import load_dotenv

project_root_env = os.path.join(os.path.dirname(__file__), "../../.env")

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    load_dotenv(override=True)


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY")
    DEBUG = os.environ.get("FLASK_DEBUG", "true").lower() == "true"
    JSON_AS_ASCII = False

    LLM_REQUEST_TIMEOUT_SECONDS = float(os.environ.get("LLM_REQUEST_TIMEOUT_SECONDS", "120"))
    LLM_FACILITY_DB_FILENAME = "llm_facility.sqlite3"
    ARCHIVE_LIBRARY_DB_FILENAME = "archive_library.sqlite3"

    ZEP_API_KEY = os.environ.get("ZEP_API_KEY")

    MAX_CONTENT_LENGTH = 100 * 1024 * 1024
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "../uploads")
    ALLOWED_EXTENSIONS = {"pdf", "md", "txt", "markdown"}

    DEFAULT_CHUNK_SIZE = 800
    DEFAULT_CHUNK_OVERLAP = 120

    NARRATIVE_DEFAULT_BRANCH_COUNT = int(os.environ.get("NARRATIVE_DEFAULT_BRANCH_COUNT", "1"))
    NARRATIVE_DEFAULT_TIMELINE_STEPS = int(os.environ.get("NARRATIVE_DEFAULT_TIMELINE_STEPS", "12"))

    @classmethod
    def validate(cls):
        return []
