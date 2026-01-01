from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from temporal.activities import (
        create_metadata_activity,
        create_frame_candidates_activity,
        rank_candidates_activity,
    )


@workflow.defn
class ProcessVideoWorkflow:
    @workflow.run
    async def run(self, video_path: str) -> None:
        await workflow.execute_activity(
            create_metadata_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=2),
        )

        await workflow.execute_activity(
            create_frame_candidates_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=5),
        )

        await workflow.execute_activity(
            rank_candidates_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=2),
        )
