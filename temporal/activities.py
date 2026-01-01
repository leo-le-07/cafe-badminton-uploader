from thumbnail_ranking import rank_candidates, RankedImage
from temporalio import activity
from video_prep import create_and_store_metadata, create_frame_candidates
from pathlib import Path


@activity.defn
async def create_metadata_activity(video_path: str) -> None:
    path = Path(video_path)
    create_and_store_metadata(path)


@activity.defn
async def create_frame_candidates_activity(video_path: str) -> int:
    path = Path(video_path)
    result = create_frame_candidates(path)
    return result


@activity.defn
async def rank_candidates_activity(video_path: str) -> list[RankedImage]:
    path = Path(video_path)
    top_ranked = rank_candidates(path)

    return top_ranked
