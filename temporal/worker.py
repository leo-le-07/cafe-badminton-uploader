from temporal.workflows import ProcessVideoWorkflow
from temporal.activities import prepare_video_activity, rank_candidates_activity
from temporal.client import get_client
from constants import TEMPORAL_TASK_QUEUE
from temporalio.worker import Worker
import asyncio


async def main():
    client = await get_client()
    worker = Worker(
        client,
        task_queue=TEMPORAL_TASK_QUEUE,
        workflows=[ProcessVideoWorkflow],
        activities=[
            prepare_video_activity,
            rank_candidates_activity,
        ],
    )

    print(f"Worker started for task queue: {TEMPORAL_TASK_QUEUE}")
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
