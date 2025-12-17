from pathlib import Path

from utils import get_metadata, get_selected_candidate_path, get_thumbnail_path


def render_thumbnail(video_path: Path):
    selected_path = get_selected_candidate_path(video_path)
    output_path = get_thumbnail_path(video_path)
    metadata = get_metadata(video_path)

    if not selected_path.exists() or not metadata:
        print(f"Missing selected thumbnail or metadata in {video_path.name}")
        return

    print(f"Template B placeholder for {video_path.name}")
    print(f"{output_path}")

