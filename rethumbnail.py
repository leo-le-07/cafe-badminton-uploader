from pathlib import Path

from utils import (
    RENDERED_THUMBNAIL_NAME,
    SELECTED_CANDIDATE_NAME,
    SUPPORTED_IMAGE_EXTENSIONS,
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
