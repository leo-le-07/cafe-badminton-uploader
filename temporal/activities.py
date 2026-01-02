from schemas import MatchMetadata
from thumbnail_ranking import rank_candidates, RankedImage
from temporalio import activity
from video_prep import create_and_store_metadata, create_frame_candidates
from pathlib import Path


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
