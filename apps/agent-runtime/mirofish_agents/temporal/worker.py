from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.assets import (
    ASSET_TASK_QUEUE,
    AssetIngestionWorkflow,
    AssetReindexWorkflow,
    StyleExtractionWorkflow,
    asset_ingestion_activity,
    asset_reindex_activity,
    style_extraction_activity,
)
from mirofish_agents.temporal.graph import (
    GRAPH_TASK_QUEUE,
    GraphBondGenerationWorkflow,
    StoryGraphBuildWorkflow,
    graph_bond_generation_activity,
    story_graph_build_activity,
)
from mirofish_agents.temporal.character import (
    CHARACTER_TASK_QUEUE,
    CharacterDialogueWorkflow,
    character_dialogue_activity,
)
from mirofish_agents.temporal.hello import (
    HELLO_AGENT_TASK_QUEUE,
    HelloAgentWorkflow,
    hello_agent_activity,
)
from mirofish_agents.temporal.seed import (
    SEED_TASK_QUEUE,
    SeedPipelineWorkflow,
    SeedSegmentRetryWorkflow,
    agent_profile_activity,
    archive_candidate_activity,
    entity_resolution_activity,
    finalize_seed_activity,
    global_aggregation_activity,
    index_assets_activity,
    ontology_activity,
    parse_file_activity,
    persist_runtime_facts_activity,
    seed_pipeline_activity,
    seed_segment_retry_activity,
    segment_text_activity,
    sequential_reading_activity,
)
from mirofish_agents.temporal.worldline import (
    WORLDLINE_TASK_QUEUE,
    WorldlinePrepareWorkflow,
    WorldlineStepWorkflow,
    worldline_prepare_activity,
    worldline_step_activity,
)
from mirofish_agents.temporal.worldline_auto_evolution import (
    WorldlineAutoEvolutionWorkflow,
    worldline_auto_evolution_finalize_activity,
    worldline_auto_evolution_step_activity,
)


def worker_components_for_task_queue(task_queue: str) -> dict[str, list[object]]:
    configured_character_task_queue = os.environ.get("CHARACTER_TASK_QUEUE", "").strip()
    if task_queue == CHARACTER_TASK_QUEUE or (
        configured_character_task_queue and task_queue == configured_character_task_queue
    ):
        return {
            "workflows": [CharacterDialogueWorkflow],
            "activities": [character_dialogue_activity],
        }
    if task_queue == ASSET_TASK_QUEUE:
        return {
            "workflows": [AssetIngestionWorkflow, StyleExtractionWorkflow, AssetReindexWorkflow],
            "activities": [asset_ingestion_activity, style_extraction_activity, asset_reindex_activity],
        }
    if task_queue == GRAPH_TASK_QUEUE:
        return {
            "workflows": [StoryGraphBuildWorkflow, GraphBondGenerationWorkflow],
            "activities": [story_graph_build_activity, graph_bond_generation_activity],
        }
    if task_queue == WORLDLINE_TASK_QUEUE:
        return {
            "workflows": [
                WorldlineStepWorkflow,
                WorldlinePrepareWorkflow,
                WorldlineAutoEvolutionWorkflow,
            ],
            "activities": [
                worldline_step_activity,
                worldline_prepare_activity,
                worldline_auto_evolution_step_activity,
                worldline_auto_evolution_finalize_activity,
            ],
        }
    configured_seed_task_queue = os.environ.get("SEED_TASK_QUEUE", "").strip()
    if task_queue == SEED_TASK_QUEUE or (
        configured_seed_task_queue and task_queue == configured_seed_task_queue
    ):
        return {
            "workflows": [SeedPipelineWorkflow, SeedSegmentRetryWorkflow],
            "activities": [
                seed_pipeline_activity,
                parse_file_activity,
                segment_text_activity,
                sequential_reading_activity,
                persist_runtime_facts_activity,
                global_aggregation_activity,
                ontology_activity,
                entity_resolution_activity,
                agent_profile_activity,
                archive_candidate_activity,
                index_assets_activity,
                finalize_seed_activity,
                seed_segment_retry_activity,
            ],
        }
    return {
        "workflows": [HelloAgentWorkflow],
        "activities": [hello_agent_activity],
    }


async def run_worker() -> None:
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233")
    temporal_namespace = os.environ.get("TEMPORAL_NAMESPACE", "default").strip() or "default"
    client = await Client.connect(temporal_address, namespace=temporal_namespace)
    task_queue = os.environ.get("AGENT_RUNTIME_TASK_QUEUE", HELLO_AGENT_TASK_QUEUE)
    components = worker_components_for_task_queue(task_queue)
    with ThreadPoolExecutor(max_workers=32) as activity_executor:
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=components["workflows"],
            activities=components["activities"],
            activity_executor=activity_executor,
        )
        await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
