import json
import shutil
from pathlib import Path

import config
from app import store
from custom_exceptions import NoUploadedRecordError
from logger import get_logger
from uploader import UPLOAD_SESSION_FILE
from utils import PROCESSED_VIDEO_NAME, get_uploaded_record, workspace_video_path

logger = get_logger(__name__)

SEGMENTS_FILE = "segments.json"
SOURCES_DIR = "sources"


def _free_path(path: Path) -> Path:
    """`path` itself, or `<stem>-<n><suffix>` next to it if that name is taken."""
    n = 1
    candidate = path
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
        n += 1
    return candidate


def archive_workspace(match_id: str) -> Path:
    """Move an uploaded match's workspace into COMPLETED_DIR.

    The encoded video and the resumable-upload session are dropped; job.json,
    metadata, thumbnails and upload.json are kept, and segments.json is added
    so the encoded video can always be rebuilt from the sources.
    """
    job = store.load_job(match_id)
    if job is None:
        raise FileNotFoundError(f"No job found for match {match_id}")
    workspace = store.workspace_dir(match_id)
    record = get_uploaded_record(workspace_video_path(workspace))
    if not record or not record.video_id:
        raise NoUploadedRecordError(f"Match {match_id} has not been uploaded")

    (workspace / PROCESSED_VIDEO_NAME).unlink(missing_ok=True)
    (workspace / UPLOAD_SESSION_FILE).unlink(missing_ok=True)
    segments = [segment.to_dict() for segment in job.match.segments]
    (workspace / SEGMENTS_FILE).write_text(
        json.dumps(segments, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    config.COMPLETED_DIR.mkdir(parents=True, exist_ok=True)
    dest = _free_path(config.COMPLETED_DIR / f"{job.recorded_date}_{match_id}")
    shutil.move(str(workspace), str(dest))
    logger.info(f"Archived workspace of {match_id} to {dest}")
    return dest


def archive_source(name: str) -> Path:
    """Move a source file from INPUT_DIR to COMPLETED_DIR/sources/."""
    if not name or name in {".", ".."} or Path(name).name != name:
        raise ValueError(f"Not a plain file name: {name!r}")
    src = config.INPUT_DIR / name
    if not src.is_file():
        raise FileNotFoundError(f"Source not found: {src}")

    dest_dir = config.COMPLETED_DIR / SOURCES_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = _free_path(dest_dir / name)
    shutil.move(str(src), str(dest))
    logger.info(f"Archived source {name} to {dest}")
    return dest
