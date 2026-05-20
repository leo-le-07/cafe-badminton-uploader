import shutil
from pathlib import Path

from auth_service import get_client
from thumbnail_enhancement.renderer import render_thumbnail
from uploader import save_upload_record, set_thumbnail
from utils import (
    RENDERED_THUMBNAIL_NAME,
    SELECTED_CANDIDATE_NAME,
    SUPPORTED_IMAGE_EXTENSIONS,
    get_uploaded_record,
)


def find_manual_thumbnail(workspace_dir: Path) -> Path:
    RESERVED = {SELECTED_CANDIDATE_NAME, RENDERED_THUMBNAIL_NAME}
    candidates = [
        f
        for f in workspace_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and f.name not in RESERVED
    ]
    if not candidates:
        raise FileNotFoundError(
            f"No manual thumbnail image found in workspace: {workspace_dir}"
        )
    return max(candidates, key=lambda f: f.stat().st_mtime)


def rethumbnail_video(workspace_dir: Path) -> None:
    fake_video_path = workspace_dir.parent / f"{workspace_dir.name}.mov"

    upload_record = get_uploaded_record(fake_video_path)
    if not upload_record or not upload_record.video_id:
        raise RuntimeError(
            f"No upload record found for workspace: {workspace_dir.name}"
        )

    manual_image = find_manual_thumbnail(workspace_dir)

    selected_path = workspace_dir / SELECTED_CANDIDATE_NAME
    shutil.copy2(str(manual_image), str(selected_path))

    thumbnail_path = workspace_dir / RENDERED_THUMBNAIL_NAME
    thumbnail_path.unlink(missing_ok=True)

    render_thumbnail(str(fake_video_path))

    youtube_client = get_client()
    set_thumbnail(youtube_client, upload_record.video_id, thumbnail_path)
    save_upload_record(fake_video_path, upload_record.video_id, thumbnail_set=True)
