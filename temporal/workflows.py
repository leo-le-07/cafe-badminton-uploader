from datetime import timedelta
from temporalio import workflow

with workflow.unsafe.imports_passed_through():
    from temporal.activities import (
        prepare_video_activity,
        rank_candidates_activity,
    )


@workflow.defn
class ProcessVideoWorkflow:
    @workflow.run
    async def run(self, video_path: str) -> None:
        await workflow.execute_activity(
            prepare_video_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=5),
        )

        top_ranked = await workflow.execute_activity(
            rank_candidates_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=2),
        )
        workflow.logger.info(
            f"Completed ranking for {video_path}, top {len(top_ranked)} candidates stored."
        )
