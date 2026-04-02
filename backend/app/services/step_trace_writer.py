"""步骤 trace bundle 的文件读写。"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any, Dict, Optional

from ..config import Config

logger = logging.getLogger(__name__)


def _traces_dir(project_id: str, task_id: str) -> str:
    return os.path.join(
        Config.UPLOAD_FOLDER, "projects", project_id, "task_traces", task_id, "steps"
    )


def _bundle_path(project_id: str, task_id: str, step_id: str) -> str:
    return os.path.join(_traces_dir(project_id, task_id), f"{step_id}.json")


def write_step_bundle(
    project_id: str,
    task_id: str,
    step_id: str,
    bundle: Dict[str, Any],
) -> None:
    """将步骤 trace bundle 原子写入磁盘。"""
    dest = _bundle_path(project_id, task_id, step_id)
    directory = os.path.dirname(dest)
    os.makedirs(directory, exist_ok=True)
    try:
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(bundle, f, ensure_ascii=False, indent=2)
            os.replace(tmp, dest)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except Exception:
        logger.exception("写入步骤 trace bundle 失败: %s/%s/%s", project_id, task_id, step_id)


def load_step_bundle(
    project_id: str,
    task_id: str,
    step_id: str,
) -> Optional[Dict[str, Any]]:
    """读取步骤 trace bundle，不存在时返回 None。"""
    path = _bundle_path(project_id, task_id, step_id)
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("读取步骤 trace bundle 失败: %s", path)
        return None
