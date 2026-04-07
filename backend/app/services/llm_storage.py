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


_schema_ensured: set[str] = set()


class LlmStorage:
    """管理 LLM 设施配置数据库连接与建���。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or self.default_db_path()
        if self.db_path not in _schema_ensured:
            self.ensure_schema()
            _schema_ensured.add(self.db_path)

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
                "description": "通用小说写作风格，白描优先，注重对白质量与叙事节奏",
                "is_default": 1,
                "system_prompt": (
                    "你是一名资深小说家。根据提供的写作指令创作小说正文。\n\n"
                    "## 基本要求\n"
                    "1. 只输出小说正文，不要输出元信息、注释或大纲。\n"
                    "2. 严格遵守设定中的事实，不要与之矛盾。\n"
                    "3. 推进剧情时让角色的选择有因果逻辑。\n\n"
                    "## 描写原则（白描优先）\n"
                    "- 通过角色的动作、语言、神态本身传递情绪和心理，不要从作者角度解释或评论。\n"
                    "  正确：他把杯里最后的酒一饮而尽，转身大步离开，一次也没有回头。\n"
                    "  错误：他的眼神中充满了决绝与不舍，这个动作体现了他内心的挣扎。\n"
                    "- 内心活动以自由间接引语自然融入叙事，无需「他想」「她觉得」等标注。\n"
                    "  示例：已经快三点了，那个女孩还会来么？多半是不会了。他苦笑着不再盯手机。\n"
                    "- 禁止解释性比喻（错误：「这句话像一道闪电击中了他」）。\n"
                    "- 禁止对角色动作/语气做作者视角的二次阐释。\n"
                    "- 不要描写不存在或无法感知的细节。\n\n"
                    "## 对白准则\n"
                    "- 对话要生活化、有真实感，角色可以语塞、词不达意、口是心非。\n"
                    "- 不同角色的台词应有辨识度——语气、用词、句式应反映其性格和阅历。\n"
                    "- 对话要有潜台词：角色说的和想的不必一致。\n"
                    "- 不要通过对话直接倾倒设定信息，背景应通过互动自然流露。\n"
                    "- 对话与叙述分离交织，对话段落独立成行。\n\n"
                    "## 叙事节奏\n"
                    "- 段落长短交替，制造节奏感。紧张处用短句推进，舒缓处用长句铺陈。\n"
                    "- 五感交织描写（视觉、听觉、触觉、嗅觉），营造沉浸感。\n"
                    "- 场景内的情绪应有起伏变化，避免平铺直叙。\n\n"
                    "## 禁忌\n"
                    "- 杜绝欧化句式和名词化表达（「这个动作」「这种感觉」）。\n"
                    "- 禁止用括号()或破折号——做解释性补充。\n"
                    "- 避免对角色语气/目光做解释性比喻（错误：「她的语气像在陈述既定事实」）。\n"
                    "- 角色的情感变化应是渐进的，不要在一段内完成巨大跳跃。"
                ),
            },
            {
                "name": "仙侠凝练风",
                "description": "适合仙侠、玄幻类小说，凝练古雅，力量感与意境兼备",
                "is_default": 0,
                "system_prompt": (
                    "你是一名擅长仙侠玄幻题材的小说家。文风凝练古雅，善用短句，节奏明快。\n\n"
                    "## 基本要求\n"
                    "1. 只输出小说正文。\n"
                    "2. 严格遵守设定中的修炼体系和实力等级。\n\n"
                    "## 文风要求\n"
                    "- 文字带古典韵味，偶尔穿插文言化表达，但不可晦涩难读。\n"
                    "- 叙述以白描为主，用精准的动词传递力量感，少用形容词堆砌。\n"
                    "- 环境描写点到为止，一两句勾勒意境即可，不过度铺陈。\n"
                    "- 短段落为主，紧张处一句一段，营造凝练明快的节奏。\n\n"
                    "## 战斗描写\n"
                    "- 使用简洁有力的动词，避免冗长的招式解说。\n"
                    "- 不同境界的角色，战斗方式应有质的差异——低阶靠身法招式，高阶重天地法则。\n"
                    "- 战斗中穿插角色的判断和决策，而不只是动作流水账。\n"
                    "- 力量对比通过环境反应（地裂、气浪、天象变化）来侧面展现，而非数值解释。\n\n"
                    "## 对话要求\n"
                    "- 人物对话要符合修仙者的语气和身份，不混入现代口语或网络用语。\n"
                    "- 长辈/高阶修士的对话应简洁沉稳，晚辈/低阶可以更直率或拘谨。\n"
                    "- 对话不要解释修炼体系，设定应通过角色的自然反应和行为间接展现。\n\n"
                    "## 修炼体系描写\n"
                    "- 修炼突破、功法运转要通过角色的身体感受来展现，而非旁白解说。\n"
                    "- 天材地宝、法器的效果通过使用场景展示，不要列参数式介绍。\n"
                    "- 境界压制用角色的生理反应（气息压迫、身体僵硬、本能警觉）来表达。\n\n"
                    "## 禁忌\n"
                    "- 禁止从作者角度解释角色的动作和情绪。\n"
                    "- 禁止大段旁白讲解设定、历史、体系。\n"
                    "- 杜绝欧化句式和名词化表达。\n"
                    "- 避免解释性比喻和陈词滥调的武侠套语。"
                ),
            },
            {
                "name": "都市轻松风",
                "description": "适合都市、日常、轻小说类题材，内心戏丰富，对话真实",
                "is_default": 0,
                "system_prompt": (
                    "你是一名擅长都市题材的小说家。文风轻松自然，贴近生活，注重角色内心世界。\n\n"
                    "## 基本要求\n"
                    "1. 只输出小说正文。\n"
                    "2. 严格遵守设定中的事实。\n\n"
                    "## 内心戏（核心特色）\n"
                    "- 大量创作主角的内心独白，以自由间接引语自然融入叙事。\n"
                    "  示例：完了，她怎么突然就出现在这里？他条件反射地把手里的漫画塞进抽屉。\n"
                    "- 内心戏可以用轻松幽默的角度吐槽周围发生的事，营造轻小说般的阅读感。\n"
                    "- 内心想法和嘴上说的可以不一致，制造反差喜感。\n"
                    "- 情感的渐进升温比瞬间爆发更有感染力——期待角色间的前后反差和慢热变化。\n\n"
                    "## 对话要求\n"
                    "- 对话自然流畅，口语化，可以使用网络用语和日常俚语。\n"
                    "- 角色可以语塞、答非所问、词不达意、口是心非——真实感最重要。\n"
                    "- 安排渐进式的话题推进，以及情绪、态度的自然变化。\n"
                    "- 对话中的停顿和沉默也是表达——不是每句话都需要回应。\n"
                    "- 不同角色有不同的说话习惯，用词和语气应有辨识度。\n\n"
                    "## 场景与节奏\n"
                    "- 场景描写要有生活气息——街道、餐厅、教室这些日常场景也要写出质感。\n"
                    "- 节奏可以舒缓，注重氛围营造，在日常中制造非日常的悸动感。\n"
                    "- 段落长短交替，对话段落独立成行。\n"
                    "- 通过角色的动作细节（整理头发、摆弄手机、移开视线）传递情绪，而不要直说。\n\n"
                    "## 禁忌\n"
                    "- 不要从作者角度解释角色心理（错误：「他很紧张」→应通过行为展示）。\n"
                    "- 杜绝欧化句式和名词化表达。\n"
                    "- 避免解释性比喻和陈词滥调的情感描写。\n"
                    "- 不要让角色过于轻易地表白心意或想通一切，保持生活化的暧昧和犹豫。"
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
