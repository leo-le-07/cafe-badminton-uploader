from pathlib import Path
import config
from collections.abc import Iterator


def scan_videos(input_path: Path, extension: str = ".mov") -> Iterator[Path]:
    videos = input_path.glob(f"*{extension}")

    return videos


def generate_metadata(video_path: Path) -> dict:
    metadata = {}

    return metadata


if __name__ == "__main__":
    scan_videos(config.INPUT_DIR)
