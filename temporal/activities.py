from thumbnail_enhancement import render_thumbnail
from schemas import MatchMetadata, UploadedRecord
from temporalio import activity
from temporalio.exceptions import ApplicationError
from video_prep import create_and_store_metadata, auto_select_thumbnail
from uploader import (
    upload_video_with_idempotency,
    set_thumbnail_for_video,
    update_video_visibility_for_video,
)
from custom_exceptions import VideoAlreadyUploadedError
from cleanup import cleanup_video
from logger import get_logger
from pathlib import Path
import config

logger = get_logger(__name__)


@activity.defn
def create_metadata_activity(video_path: str) -> MatchMetadata:
    return create_and_store_metadata(video_path)


@activity.defn
def render_thumbnail_activity(video_path: str) -> str:
    return render_thumbnail(video_path)


@activity.defn
def upload_video_activity(video_path: str) -> UploadedRecord:
    def heartbeat(progress: float) -> None:
        activity.heartbeat(f"Upload progress: {progress:.1f}%")

    try:
        logger.info(f"Uploading video: {video_path}")
        result = upload_video_with_idempotency(video_path, heartbeat)
        logger.info(f"Uploaded video: {video_path}")
        return result
    except VideoAlreadyUploadedError as e:
        raise ApplicationError(
            str(e),
            type="VideoAlreadyUploadedError",
            non_retryable=True,
        )


@activity.defn
def set_thumbnail_activity(video_path: str) -> None:
    set_thumbnail_for_video(video_path)


@activity.defn
def update_video_visibility_activity(video_path: str) -> None:
    update_video_visibility_for_video(video_path)


@activity.defn
def cleanup_activity(video_path: str) -> str:
    return cleanup_video(video_path)


@activity.defn
def auto_select_thumbnail_activity(video_path: str) -> None:
    auto_select_thumbnail(video_path)
