"""LLM 设施 SQLite 存储。"""

from __future__ import annotations

import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from ..config import Config


CREATE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS llm_channels (
        channel_key TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        base_url TEXT NOT NULL,
        api_key TEXT NOT NULL,
        max_concurrency INTEGER NOT NULL DEFAULT 4,
        is_enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_sync_at TEXT,
        last_sync_status TEXT NOT NULL DEFAULT 'idle',
        last_sync_error TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_models (
        channel_key TEXT NOT NULL,
        model_id TEXT NOT NULL,
        owned_by TEXT,
        fetched_at TEXT NOT NULL,
        raw_payload TEXT NOT NULL,
        PRIMARY KEY (channel_key, model_id),
        FOREIGN KEY (channel_key) REFERENCES llm_channels(channel_key) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS llm_module_bindings (
        module_key TEXT PRIMARY KEY,
        channel_key TEXT NOT NULL,
        model_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (channel_key) REFERENCES llm_channels(channel_key) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS writer_presets (
        preset_id TEXT PRIMARY KEY,
        project_id TEXT,
        name TEXT NOT NULL,
        description TEXT DEFAULT '',
        system_prompt TEXT NOT NULL,
        is_default INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
)


class LlmStorage:
    """管理 LLM 设施配置数据库连接与建表。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.default_db_path()
        self.ensure_schema()

    @classmethod
    def default_db_path(cls) -> str:
        return os.path.join(
            Config.UPLOAD_FOLDER,
            "system",
            Config.LLM_FACILITY_DB_FILENAME,
        )

    def ensure_schema(self) -> None:
        self._ensure_parent_dir()
        with self.connect() as connection:
            for statement in CREATE_STATEMENTS:
                connection.execute(statement)
            self._ensure_llm_channel_columns(connection)
            self._seed_default_writer_presets(connection)
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_parent_dir()
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
        finally:
            connection.close()

    def _ensure_parent_dir(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _ensure_llm_channel_columns(self, connection: sqlite3.Connection) -> None:
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(llm_channels)").fetchall()
        }
        if "max_concurrency" not in existing:
            connection.execute(
                """
                ALTER TABLE llm_channels
                ADD COLUMN max_concurrency INTEGER NOT NULL DEFAULT 4
                """
            )

    def _seed_default_writer_presets(self, connection: sqlite3.Connection) -> None:
        count = connection.execute(
            "SELECT COUNT(*) FROM writer_presets"
        ).fetchone()[0]
        if count > 0:
            return

        now = datetime.now(timezone.utc).isoformat()
        defaults = [
            {
                "name": "通用写作",
                "description": "通用小说写作风格",
                "is_default": 1,
                "system_prompt": (
                    "你是一名资深小说家。根据提供的写作指令创作小说正文。\n\n"
                    "要求：\n"
                    "1. 只输出小说正文，不要输出元信息、注释或大纲。\n"
                    "2. 场景描写要有画面感，对话要贴合角色性格。\n"
                    "3. 严格遵守设定中的事实，不要与之矛盾。\n"
                    "4. 推进剧情时让角色的选择有因果逻辑。"
                ),
            },
            {
                "name": "仙侠凝练风",
                "description": "适合仙侠、玄幻类小说的凝练风格",
                "is_default": 0,
                "system_prompt": (
                    "你是一名擅长仙侠玄幻题材的小说家。文风要求凝练古雅，善用短句，节奏明快。\n\n"
                    "要求：\n"
                    "1. 只输出小说正文。\n"
                    "2. 战斗场面要有画面感和力量感，使用简洁有力的动词。\n"
                    "3. 人物对话要符合修仙者的语气和身份。\n"
                    "4. 环境描写点到为止，不过度铺陈。\n"
                    "5. 严格遵守设定中的修炼体系和实力等级。"
                ),
            },
            {
                "name": "都市轻松风",
                "description": "适合都市、日常类小说的轻松风格",
                "is_default": 0,
                "system_prompt": (
                    "你是一名擅长都市题材的小说家。文风要求轻松自然，贴近生活，对话口语化。\n\n"
                    "要求：\n"
                    "1. 只输出小说正文。\n"
                    "2. 对话要自然流畅，可以使用网络用语和口语表达。\n"
                    "3. 注重人物的内心活动和情感细节。\n"
                    "4. 场景描写要有生活气息。\n"
                    "5. 节奏可以舒缓，注重氛围营造。"
                ),
            },
        ]

        for preset in defaults:
            connection.execute(
                """
                INSERT INTO writer_presets
                    (preset_id, project_id, name, description, system_prompt,
                     is_default, created_at, updated_at)
                VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    preset["name"],
                    preset["description"],
                    preset["system_prompt"],
                    preset["is_default"],
                    now,
                    now,
                ),
            )
