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

    # 深度阅读(sequential_reader) 段级重试策略
    SEED_SEGMENT_RETRY_MAX_ATTEMPTS: int = 2
    SEED_SEGMENT_RETRY_INITIAL_DELAY_SECONDS: float = 10.0
    SEED_SEGMENT_RETRY_MAX_DELAY_SECONDS: float = 30.0
    SEED_STAGE_COOLDOWN_STREAK: int = 3
    SEED_STAGE_COOLDOWN_SECONDS: float = 30.0
    SEED_SWEEP_ENABLED: bool = True

    # 启动时自动续跑上一次被杀的种子任务：
    # _recover_stale_tasks 先把僵尸 task 标为 failed，然后对每个在 stage 2
    # 之后（即 smart_segments.json 已落盘）的项目，自动触发 create_retry_task
    # 把 reading_notes / 弧卷摘要 / 下游产物一并补齐。默认关闭 —— 希望"无感
    # 续跑"的部署可以显式打开。
    SEED_AUTO_RESUME_ON_STARTUP: bool = False

    # 启动时自动回填：扫描"种子已完成但档案库空"的老项目，后台跑 GlobalDataLinker
    GLOBAL_DATA_BACKFILL_ON_STARTUP: bool = True
    GLOBAL_DATA_BACKFILL_USE_LLM: bool = True

    # 种子管线完成后是否自动串联档案库 / 图谱 / FTS
    # 默认 True 以兑现"种子完成即全局可用"的产品承诺;
    # 少量测试(test_local_story_graph_pipeline 等)验证独立 /build-graph 流程,
    # 关掉此开关保留旧行为。
    SEED_AUTO_LINK_GLOBAL_DATA: bool = True

    # Phase E — 防止 LLM 返回数据被隐式截断丢失
    SEED_MAX_EVIDENCE_PER_ITEM: int = 10
    SEED_MAX_CHAPTER_BEATS: int = 50
    SEED_RECENT_SUMMARIES_WINDOW: int = 5
    SEED_ONTOLOGY_CHUNK_SIZE: int = 51200
    SEED_CHARACTER_PROFILE_ARC_WINDOW: int = 10
    SEED_CHARACTER_PROFILE_VOLUME_WINDOW: int = 5

    # 图谱管线放宽参数 —— 降低各层数据衰减，让配角 / 道具 / 事件 不被硬阈值吞掉
    SEED_MENTION_MIN_PROTAGONIST: int = 3
    SEED_MENTION_MIN_MAJOR: int = 1
    SEED_ORG_MENTION_MIN_MAJOR: int = 1
    SEED_PROFILE_IMPORTANCE_THRESHOLD: int = 1
    GRAPH_ARTIFACT_EDGE_PAIR_LIMIT: int = 8
    GRAPH_EVENT_EVIDENCE_LIMIT: int = 5
    GRAPH_ARTIFACT_CANDIDATE_LIMIT: int = 8
    GRAPH_EVENT_CANDIDATE_EVIDENCE_LIMIT: int = 5


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
