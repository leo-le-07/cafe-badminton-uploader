import config
from pathlib import Path
from collections.abc import Iterator
import json

CANDIDATES_DIR = "candidates"
METADATA_FILE = "metadata.json"
SELECTED_CANDIDATE_NAME = "selected.jpg"
RENDERED_THUMBNAIL_NAME = "thumbnail.jpg"


def scan_videos(input_path: Path) -> Iterator[Path]:
    return (
        video
        for video in input_path.iterdir()
        if video.is_file() and video.suffix in {".mov", ".MOV"}
    )


def get_workspace_dir(video_path: Path) -> Path:
    return config.INPUT_DIR / video_path.stem


def get_candidate_dir(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / CANDIDATES_DIR


def get_metadata_path(video_path: Path) -> Path:
    return get_candidate_dir(video_path) / METADATA_FILE


def get_selected_candidate_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / SELECTED_CANDIDATE_NAME


def get_thumbnail_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / RENDERED_THUMBNAIL_NAME


def get_metadata(video_path: Path):
    metadata_path = get_metadata_path(video_path)
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    return metadata


def get_upload_record_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / "upload.json"
