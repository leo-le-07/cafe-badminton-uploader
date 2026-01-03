import config
import shutil
from pathlib import Path

from utils import get_workspace_dir, scan_videos, get_uploaded_record
from logger import get_logger

logger = get_logger(__name__)


def cleanup_video(video_path: Path) -> None:
    uploaded_record = get_uploaded_record(video_path)

    if not uploaded_record:
        logger.info(f"Skipping {video_path.name}: no upload record found")
        return

    workspace_dir = get_workspace_dir(video_path)

    if not workspace_dir.exists():
        logger.info(f"Skipping {video_path.name}: workspace directory not found")
        return

    try:
        video_dest = config.COMPLETED_DIR / video_path.name
        workspace_dest = config.COMPLETED_DIR / workspace_dir.name

        shutil.move(str(video_path), str(video_dest))
        shutil.move(str(workspace_dir), str(workspace_dest))

        logger.info(f"Moved {video_path.name} and workspace to {config.COMPLETED_DIR}")
    except Exception as e:
        logger.error(f"Failed to move {video_path.name}: {e}")
        raise


def cleanup_uploaded_videos():
    videos = list(scan_videos(config.INPUT_DIR))
    moved_count = 0

    for video_path in videos:
        try:
            cleanup_video(video_path)
            moved_count += 1
        except Exception:
            continue

    logger.info(
        f"Completed: Moved {moved_count} uploaded video(s) to {config.COMPLETED_DIR}"
    )


def run():
    cleanup_uploaded_videos()


if __name__ == "__main__":
    run()
