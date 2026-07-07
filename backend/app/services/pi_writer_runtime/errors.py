"""Structured errors for the writer runtime compatibility bridge."""

from __future__ import annotations


class WriterRunError(Exception):
    code = "WORKFLOW_FAILED"

    def __init__(self, message: str, *, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class LlmModuleUnboundError(WriterRunError):
    code = "LLM_MODULE_UNBOUND"

    def __init__(self, module_key: str, message: str):
        super().__init__(message, details={"module_key": module_key})
        self.module_key = module_key


class ToolPermissionDeniedError(WriterRunError):
    code = "TOOL_PERMISSION_DENIED"
