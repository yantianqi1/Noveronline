"""
世界线引擎装配入口
"""

from typing import Optional

from .agent_memory_service import AgentMemoryService
from .archive_library_service import ArchiveLibraryService
from .world_state_store import WorldStateStore
from .worldline_agent_registry import WorldlineAgentRegistry
from .worldline_branch_comparison import WorldlineBranchComparisonService
from .worldline_branch_service import WorldlineBranchService
from .worldline_engine import WorldlineEngine
from .worldline_runtime_service import WorldlineRuntimeService
from .worldline_source_loader import WorldlineSourceLoader


def build_worldline_engine(store: Optional[WorldStateStore] = None) -> WorldlineEngine:
    resolved_store = store or WorldStateStore()
    registry = WorldlineAgentRegistry()
    memory_service = AgentMemoryService()
    return WorldlineEngine(
        store=resolved_store,
        source_loader=WorldlineSourceLoader(resolved_store),
        branch_service=WorldlineBranchService(agent_registry=registry),
        comparison_service=WorldlineBranchComparisonService(),
        archive_library=ArchiveLibraryService(),
        runtime_service=WorldlineRuntimeService(registry=registry, memory_service=memory_service),
        memory_service=memory_service,
    )
