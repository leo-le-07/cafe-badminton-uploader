import config
import shutil
from pathlib import Path

from utils import get_upload_record_path, get_workspace_dir, scan_videos


def cleanup_uploaded_videos():
    videos = list(scan_videos(config.INPUT_DIR))
    moved_count = 0

    for video_path in videos:
        upload_record_path = get_upload_record_path(video_path)

        if not upload_record_path.exists():
            continue

        workspace_dir = get_workspace_dir(video_path)

        if not workspace_dir.exists():
            continue

        try:
            video_dest = config.COMPLETED_DIR / video_path.name
            workspace_dest = config.COMPLETED_DIR / workspace_dir.name

            shutil.move(str(video_path), str(video_dest))
            shutil.move(str(workspace_dir), str(workspace_dest))

            moved_count += 1
        except Exception as e:
            print(f"✗ Failed to move {video_path.name}: {e}")

    print(f"\nCompleted: Moved {moved_count} uploaded video(s) to {config.COMPLETED_DIR}")


def run():
    cleanup_uploaded_videos()


if __name__ == "__main__":
    run()

