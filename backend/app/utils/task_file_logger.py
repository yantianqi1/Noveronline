"""Per-task log file writer.

Creates a log file at <project_dir>/task_logs/<task_id>.log.
Format: [YYYY-MM-DD HH:MM:SS] [LEVEL] [stage] message
"""
import json
import logging
import os


class _StageFormatter(logging.Formatter):
    """Custom formatter that injects [LEVEL] and [stage] tokens."""

    LEVEL_LABELS = {
        logging.INFO: "INFO",
        logging.WARNING: "WARN",
        logging.ERROR: "ERROR",
        logging.DEBUG: "DEBUG",
    }

    def format(self, record: logging.LogRecord) -> str:
        ts = self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S")
        level = self.LEVEL_LABELS.get(record.levelno, record.levelname)
        stage = getattr(record, "stage", "")
        return f"[{ts}] [{level}] [{stage}] {record.getMessage()}"


class TaskFileLogger:
    """Writes structured log entries for a single task run to a dedicated file."""

    def __init__(self, project_dir: str, task_id: str):
        log_dir = os.path.join(project_dir, "task_logs")
        os.makedirs(log_dir, exist_ok=True)

        log_path = os.path.join(log_dir, f"{task_id}.log")

        self._logger = logging.getLogger(f"task.{task_id}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False

        self._handler = logging.FileHandler(log_path, encoding="utf-8")
        self._handler.setFormatter(_StageFormatter())
        self._logger.addHandler(self._handler)

    # ------------------------------------------------------------------
    # Core log methods
    # ------------------------------------------------------------------

    def _log(self, level: int, stage: str, message: str) -> None:
        extra = {"stage": stage}
        self._logger.log(level, message, extra=extra)

    def info(self, stage: str, message: str) -> None:
        self._log(logging.INFO, stage, message)

    def warning(self, stage: str, message: str) -> None:
        self._log(logging.WARNING, stage, message)

    def error(self, stage: str, message: str) -> None:
        self._log(logging.ERROR, stage, message)

    # ------------------------------------------------------------------
    # Stage lifecycle helpers
    # ------------------------------------------------------------------

    def stage_start(self, stage: str, detail: str = "") -> None:
        msg = f"START" if not detail else f"START — {detail}"
        self.info(stage, msg)

    def stage_end(self, stage: str, elapsed_s: float = 0, detail: str = "") -> None:
        parts = [f"END ({elapsed_s:.3f}s)"]
        if detail:
            parts.append(detail)
        self.info(stage, " — ".join(parts))

    # ------------------------------------------------------------------
    # LLM call logging
    # ------------------------------------------------------------------

    def log_llm_call(
        self,
        stage: str,
        module: str,
        model: str,
        prompt: str,
        response: str,
        elapsed_ms: int,
    ) -> None:
        """Log an LLM call with truncated previews (prompt: 500 chars, response: 1000 chars)."""
        summary = (
            f"LLM call — module={module} model={model} elapsed_ms={elapsed_ms} "
            f"prompt_chars={len(prompt)} response_chars={len(response)}"
        )
        self.info(stage, summary)

        detail = {
            "module": module,
            "model": model,
            "elapsed_ms": elapsed_ms,
            "prompt_preview": prompt[:500],
            "response_preview": response[:1000],
            "prompt_chars": len(prompt),
            "response_chars": len(response),
        }
        json_block = json.dumps(detail, ensure_ascii=False, indent=2)
        # Indent every line with 2 spaces so it's visually nested in the log
        indented = "\n".join("  " + line for line in json_block.splitlines())
        self._handler.stream.write(indented + "\n")
        self._handler.stream.flush()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the file handler. Idempotent."""
        if self._handler in self._logger.handlers:
            self._handler.close()
            self._logger.removeHandler(self._handler)
