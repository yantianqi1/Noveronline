from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

from temporalio.client import Client
from temporalio.worker import Worker

from mirofish_agents.temporal.graph import GRAPH_TASK_QUEUE
from mirofish_agents.temporal.worker import worker_components_for_task_queue


async def run() -> None:
    temporal_address = os.environ.get("TEMPORAL_ADDRESS", "127.0.0.1:7233")
    task_queue = os.environ.get("MIROFISH_GRAPH_LIVE_TASK_QUEUE", "graph-browser-live")
    components = worker_components_for_task_queue(GRAPH_TASK_QUEUE)
    client = await Client.connect(temporal_address)
    with ThreadPoolExecutor(max_workers=8) as activity_executor:
        worker = Worker(
            client,
            task_queue=task_queue,
            workflows=components["workflows"],
            activities=components["activities"],
            activity_executor=activity_executor,
        )
        await worker.run()


if __name__ == "__main__":
    asyncio.run(run())
