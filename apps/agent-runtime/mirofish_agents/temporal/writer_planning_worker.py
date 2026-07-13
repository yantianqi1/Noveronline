from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.manuscript_asset_distillation import (
    ManuscriptAssetDistillationWorkflow,
    distill_manuscript_assets_activity,
    finalize_distillation_activity,
    manuscript_asset_distillation_failure_activity,
    validate_distillation_source_activity,
)
from mirofish_agents.temporal.writer_planning import (
    WRITER_PLANNING_TASK_QUEUE,
    WriterBookPlanWorkflow,
    WriterDedupExtractionWorkflow,
    writer_book_plan_activity,
    writer_dedup_activity,
    writer_planning_failure_activity,
)


async def run_worker() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233").strip()
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default").strip()
    task_queue = os.environ.get("WRITER_PLANNING_TASK_QUEUE", WRITER_PLANNING_TASK_QUEUE).strip()
    client = await Client.connect(address, namespace=namespace)
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=[
                WriterDedupExtractionWorkflow,
                WriterBookPlanWorkflow,
                ManuscriptAssetDistillationWorkflow,
            ],
            activities=[
                writer_dedup_activity,
                writer_book_plan_activity,
                writer_planning_failure_activity,
                validate_distillation_source_activity,
                distill_manuscript_assets_activity,
                finalize_distillation_activity,
                manuscript_asset_distillation_failure_activity,
            ],
            activity_executor=executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
