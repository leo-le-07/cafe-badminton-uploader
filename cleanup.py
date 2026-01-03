import config
import shutil
from pathlib import Path

from utils import get_workspace_dir, scan_videos, get_uploaded_record
from logger import get_logger
from custom_exceptions import NoUploadedRecordError

logger = get_logger(__name__)


def cleanup_video(video_path: Path) -> str:
    uploaded_record = get_uploaded_record(video_path)

    if not uploaded_record or not uploaded_record.video_id:
        raise NoUploadedRecordError

    workspace_dir = get_workspace_dir(video_path)

    if not workspace_dir.exists():
        raise NoUploadedRecordError

    video_dest = config.COMPLETED_DIR / video_path.name
    workspace_dest = config.COMPLETED_DIR / workspace_dir.name

    shutil.move(str(video_path), str(video_dest))
    shutil.move(str(workspace_dir), str(workspace_dest))

    return str(video_dest)


def cleanup_uploaded_videos() -> int:
    videos = list(scan_videos(config.INPUT_DIR))
    moved_count = 0

    for video_path in videos:
        try:
            cleanup_video(video_path)
            moved_count += 1
        except (NoUploadedRecordError, Exception):
            continue
    return moved_count


def run():
    moved_count = cleanup_uploaded_videos()
    logger.info(f"Moved {moved_count} uploaded video(s) to {config.COMPLETED_DIR}")


if __name__ == "__main__":
    run()
