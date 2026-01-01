from thumbnail_ranking import rank_candidates, RankedImage
from temporalio import activity
from video_prep import prepare_video
from pathlib import Path


@activity.defn
async def prepare_video_activity(video_path: str):
    path = Path(video_path)
    prepare_video(path)


@activity.defn
async def rank_candidates_activity(video_path: str) -> list[RankedImage]:
    path = Path(video_path)
    top_ranked = rank_candidates(path)

    return top_ranked
