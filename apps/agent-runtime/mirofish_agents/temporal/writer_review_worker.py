from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.writer_review import (
    WRITER_REVIEW_TASK_QUEUE,
    WriterReviewWorkflow,
    writer_review_activity,
)


async def run_worker() -> None:
    address = os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233").strip()
    namespace = os.environ.get("TEMPORAL_NAMESPACE", "default").strip()
    task_queue = os.environ.get("WRITER_REVIEW_TASK_QUEUE", WRITER_REVIEW_TASK_QUEUE).strip()
    client = await Client.connect(address, namespace=namespace)
    with ThreadPoolExecutor(max_workers=4) as executor:
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=[WriterReviewWorkflow],
            activities=[writer_review_activity],
            activity_executor=executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
