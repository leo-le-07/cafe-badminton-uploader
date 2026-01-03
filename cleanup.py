import config
import shutil
from pathlib import Path

from utils import get_workspace_dir, get_uploaded_record
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
