from concurrent.futures import ThreadPoolExecutor
from temporal.workflows import ProcessVideoWorkflow
from temporal.activities import (
    create_metadata_activity,
    create_frame_candidates_activity,
    rank_candidates_activity,
    render_thumbnail_activity,
    upload_video_activity,
    set_thumbnail_activity,
)
from temporal.client import get_client
from constants import TEMPORAL_TASK_QUEUE
from temporalio.worker import Worker
import asyncio


async def main():
    client = await get_client()
    with ThreadPoolExecutor(max_workers=8) as executor:
        worker = Worker(
            client,
            task_queue=TEMPORAL_TASK_QUEUE,
            workflows=[ProcessVideoWorkflow],
            activities=[
                create_metadata_activity,
                create_frame_candidates_activity,
                rank_candidates_activity,
                render_thumbnail_activity,
                upload_video_activity,
                set_thumbnail_activity,
            ],
            activity_executor=executor,
        )

        print(f"Worker started for task queue: {TEMPORAL_TASK_QUEUE}")
        await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
