from schemas import MatchMetadata, UploadedRecord
from custom_exceptions import CorruptUploadRecordError
from pathlib import Path
from collections.abc import Iterator
import json
import os
import tempfile

METADATA_FILE = "metadata.json"
SELECTED_CANDIDATE_NAME = "selected.jpg"
RENDERED_THUMBNAIL_NAME = "thumbnail.jpg"
PROCESSED_VIDEO_NAME = "processed.mov"
UPLOADED_FILE = "upload.json"
SUPPORTED_VIDEO_EXTENSIONS = {".mov", ".mp4"}
SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tiff",
    ".tif",
    ".gif",
    ".heic",
    ".heif",
}


def scan_videos(input_path: Path) -> Iterator[Path]:
    return (
        video
        for video in input_path.iterdir()
        if video.is_file() and video.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS
    )


def get_workspace_dir(video_path: Path) -> Path:
    return video_path.parent / video_path.stem


def workspace_video_path(workspace_dir: Path) -> Path:
    return workspace_dir.parent / f"{workspace_dir.name}.mov"


def get_metadata_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / METADATA_FILE


def get_selected_candidate_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / SELECTED_CANDIDATE_NAME


def get_thumbnail_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / RENDERED_THUMBNAIL_NAME


def get_processed_video_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / PROCESSED_VIDEO_NAME


def get_metadata(video_path: Path) -> MatchMetadata:
    metadata_path = get_metadata_path(video_path)
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata_dict = json.load(f)

    return MatchMetadata(**metadata_dict)


def write_json_atomic(path: Path, data, indent: int = 2) -> None:
    """Write JSON to a temp file next to `path`, then move it into place, so
    a crash never leaves a half-written file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=indent)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def get_upload_record_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / UPLOADED_FILE


def get_uploaded_record(video_path: Path) -> UploadedRecord | None:
    """The workspace's upload record; None when there is none.

    Raises CorruptUploadRecordError when the file exists but cannot be read:
    the video may or may not be on YouTube, so callers must neither upload
    nor discard the workspace."""
    upload_record_path = get_upload_record_path(video_path)
    if not upload_record_path.exists():
        return None
    try:
        with open(upload_record_path, "r", encoding="utf-8") as f:
            upload_record_dict = json.load(f)
        return UploadedRecord(**upload_record_dict)
    except (OSError, ValueError, TypeError) as e:
        raise CorruptUploadRecordError(
            f"File {UPLOADED_FILE} trong {upload_record_path.parent} bị hỏng, "
            "không đọc được. Kiểm tra trên YouTube xem video đã lên chưa rồi "
            f"sửa hoặc xoá file này trước khi thử lại ({e})"
        ) from e
