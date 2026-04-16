"""SQLAlchemy table registry."""

from .base import metadata
from . import archive, assets, fts, graph, llm, novel, search, task, worldline  # noqa: F401

__all__ = ["metadata"]
