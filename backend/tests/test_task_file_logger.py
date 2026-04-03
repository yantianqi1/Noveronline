"""Tests for TaskFileLogger utility."""
import json
import os
import pytest

from app.utils.task_file_logger import TaskFileLogger


def _read_log(tmp_path, task_id):
    log_path = tmp_path / "task_logs" / f"{task_id}.log"
    return log_path.read_text(encoding="utf-8")


def test_creates_log_file(tmp_path):
    """Logger creates file at correct path; content includes message and stage."""
    logger = TaskFileLogger(str(tmp_path), "task-001")
    logger.info("init", "hello world")
    logger.close()

    log_path = tmp_path / "task_logs" / "task-001.log"
    assert log_path.exists(), "Log file should be created at <project_dir>/task_logs/<task_id>.log"

    content = log_path.read_text(encoding="utf-8")
    assert "init" in content
    assert "hello world" in content


def test_log_levels(tmp_path):
    """info/warning/error all produce [INFO]/[WARN]/[ERROR] in output."""
    logger = TaskFileLogger(str(tmp_path), "task-002")
    logger.info("stage_a", "an info message")
    logger.warning("stage_b", "a warning message")
    logger.error("stage_c", "an error message")
    logger.close()

    content = _read_log(tmp_path, "task-002")
    assert "[INFO]" in content
    assert "[WARN]" in content
    assert "[ERROR]" in content
    assert "an info message" in content
    assert "a warning message" in content
    assert "an error message" in content


def test_log_llm_call(tmp_path):
    """log_llm_call logs model name, elapsed, truncated previews with char counts."""
    logger = TaskFileLogger(str(tmp_path), "task-003")

    long_prompt = "A" * 2000
    long_response = "B" * 5000

    logger.log_llm_call(
        stage="sequential_reading",
        module="sequential_reading",
        model="deepseek-chat",
        prompt=long_prompt,
        response=long_response,
        elapsed_ms=12345,
    )
    logger.close()

    content = _read_log(tmp_path, "task-003")

    # Model and elapsed should appear
    assert "deepseek-chat" in content
    assert "12345" in content

    # Should contain a JSON block — find and parse it
    # The JSON block starts with "  {" (indented)
    lines = content.splitlines()
    json_lines = []
    in_block = False
    for line in lines:
        if line.startswith("  {"):
            in_block = True
        if in_block:
            json_lines.append(line)
        if in_block and line.strip() == "}":
            break

    assert json_lines, "Should contain an indented JSON block"
    json_text = "\n".join(l[2:] for l in json_lines)  # strip 2-space indent
    data = json.loads(json_text)

    assert data["model"] == "deepseek-chat"
    assert data["elapsed_ms"] == 12345
    assert data["prompt_chars"] == 2000
    assert data["response_chars"] == 5000
    assert len(data["prompt_preview"]) <= 500
    assert len(data["response_preview"]) <= 1000
    assert data["prompt_preview"] == "A" * 500
    assert data["response_preview"] == "B" * 1000


def test_log_stage_timing(tmp_path):
    """stage_start + stage_end logs elapsed time."""
    logger = TaskFileLogger(str(tmp_path), "task-004")
    logger.stage_start("extraction", "starting extraction")
    logger.stage_end("extraction", elapsed_s=3.14, detail="done")
    logger.close()

    content = _read_log(tmp_path, "task-004")
    assert "extraction" in content
    assert "3.14" in content


def test_close_is_idempotent(tmp_path):
    """Calling close() twice does not raise."""
    logger = TaskFileLogger(str(tmp_path), "task-005")
    logger.info("test", "message")
    logger.close()
    logger.close()  # Should not raise
