from thumbnail_enhancement import render_thumbnail
from schemas import MatchMetadata, UploadedRecord
from thumbnail_ranking import rank_candidates, RankedImage
from temporalio import activity
from temporalio.exceptions import ApplicationError
from video_prep import create_and_store_metadata, create_frame_candidates
from pathlib import Path
from uploader import (
    upload_video_with_idempotency,
    set_thumbnail_for_video,
    update_video_visibility_for_video,
)
from custom_exceptions import VideoAlreadyUploadedError
from cleanup import cleanup_video


@activity.defn
def create_metadata_activity(video_path: str) -> MatchMetadata:
    path = Path(video_path)
    return create_and_store_metadata(path)


@activity.defn
def create_frame_candidates_activity(video_path: str) -> int:
    path = Path(video_path)
    result = create_frame_candidates(path)
    return result


@activity.defn
def rank_candidates_activity(video_path: str) -> list[RankedImage]:
    path = Path(video_path)
    top_ranked = rank_candidates(path)

    return top_ranked


@activity.defn
def render_thumbnail_activity(video_path: str) -> str:
    path = Path(video_path)
    return render_thumbnail(path)


@activity.defn
def upload_video_activity(video_path: str) -> UploadedRecord:
    path = Path(video_path)

    def heartbeat(progress: float) -> None:
        activity.heartbeat(f"Upload progress: {progress:.1f}%")

    try:
        return upload_video_with_idempotency(path, heartbeat)
    except VideoAlreadyUploadedError as e:
        raise ApplicationError(
            str(e),
            type="VideoAlreadyUploadedError",
            non_retryable=True,
        )


@activity.defn
def set_thumbnail_activity(video_path: str) -> None:
    path = Path(video_path)
    set_thumbnail_for_video(path)


@activity.defn
def update_video_visibility_activity(video_path: str) -> None:
    path = Path(video_path)
    update_video_visibility_for_video(path)


@activity.defn
def cleanup_activity(video_path: str) -> str:
    path = Path(video_path)
    return cleanup_video(path)
