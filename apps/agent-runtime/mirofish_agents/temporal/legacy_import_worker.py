from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from .legacy_import_workflow import (
    LEGACY_IMPORT_TASK_QUEUE,
    LegacyImportWorkflow,
    legacy_import_apply_activity,
    legacy_import_plan_activity,
    legacy_import_verify_activity,
)


async def run_worker() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233")
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default")
    task_queue = os.environ.get("LEGACY_IMPORT_TASK_QUEUE", LEGACY_IMPORT_TASK_QUEUE)
    client = await Client.connect(address, namespace=namespace)
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=[LegacyImportWorkflow],
            activities=[
                legacy_import_plan_activity,
                legacy_import_apply_activity,
                legacy_import_verify_activity,
            ],
            activity_executor=executor,
        )
        await worker.run()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
