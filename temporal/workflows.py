from datetime import timedelta
from temporalio import workflow

from constants import (
    WORKFLOW_STAGE_INITIALIZING,
    WORKFLOW_STAGE_CREATING_METADATA,
    WORKFLOW_STAGE_EXTRACTING_FRAMES,
    WORKFLOW_STAGE_RANKING_CANDIDATES,
    WORKFLOW_STAGE_WAITING_FOR_SELECTION,
    WORKFLOW_STAGE_SELECTED,
    WORKFLOW_STAGE_ENHANCING_THUMBNAIL,
    WORKFLOW_STAGE_UPLOADING,
    WORKFLOW_STAGE_SETTING_THUMBNAIL,
    WORKFLOW_STAGE_UPDATING_VISIBILITY,
    WORKFLOW_STAGE_COMPLETED,
)

with workflow.unsafe.imports_passed_through():
    from temporal.activities import (
        create_metadata_activity,
        create_frame_candidates_activity,
        rank_candidates_activity,
        render_thumbnail_activity,
        upload_video_activity,
        set_thumbnail_activity,
        update_video_visibility_activity,
        cleanup_activity,
    )


@workflow.defn
class ProcessVideoWorkflow:
    def __init__(self):
        self.selected: bool = False
        self.stage: str = WORKFLOW_STAGE_INITIALIZING
        self.video_path: str = ""

    @workflow.signal
    def thumbnail_selected(self) -> None:
        self.selected = True
        self.stage = WORKFLOW_STAGE_SELECTED

    @workflow.query
    def get_stage(self) -> str:
        return self.stage

    @workflow.query
    def get_video_path(self) -> str:
        return self.video_path

    @workflow.run
    async def run(self, video_path: str) -> None:
        workflow.logger.info(f"Running workflow for {video_path}")

        self.video_path = video_path

        self.stage = WORKFLOW_STAGE_CREATING_METADATA
        await workflow.execute_activity(
            create_metadata_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=5),
        )

        self.stage = WORKFLOW_STAGE_UPLOADING
        await workflow.execute_activity(
            upload_video_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=120),
        )

        self.stage = WORKFLOW_STAGE_EXTRACTING_FRAMES
        await workflow.execute_activity(
            create_frame_candidates_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=30),
        )

        self.stage = WORKFLOW_STAGE_RANKING_CANDIDATES
        await workflow.execute_activity(
            rank_candidates_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=30),
        )

        self.stage = WORKFLOW_STAGE_WAITING_FOR_SELECTION
        workflow.logger.info(f"Waiting for thumbnail selection for {video_path}")
        await workflow.wait_condition(lambda: self.selected)

        self.stage = WORKFLOW_STAGE_ENHANCING_THUMBNAIL
        await workflow.execute_activity(
            render_thumbnail_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=10),
        )

        self.stage = WORKFLOW_STAGE_SETTING_THUMBNAIL
        await workflow.execute_activity(
            set_thumbnail_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=5),
        )

        self.stage = WORKFLOW_STAGE_UPDATING_VISIBILITY
        await workflow.execute_activity(
            update_video_visibility_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=5),
        )

        self.stage = WORKFLOW_STAGE_COMPLETED
        await workflow.execute_activity(
            cleanup_activity,
            video_path,
            start_to_close_timeout=timedelta(minutes=5),
        )

        workflow.logger.info(f"Workflow completed for {video_path}")
