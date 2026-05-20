# Manual Thumbnail Replacement

**Date:** 2026-05-20
**Status:** Approved

## Problem

After a video completes the full upload pipeline and is moved to `COMPLETED_DIR`, there is no way to replace its YouTube thumbnail without re-running the entire workflow. The user needs a lightweight post-completion command to swap in a manually chosen image, re-render it through the template system, and push the result to YouTube.

## Solution

A new `rethumbnail` CLI command that detects a manually dropped image in the completed workspace, renders it through the existing template pipeline, and sets it as the YouTube thumbnail.

## Background: Workspace Structure

Each video has a workspace folder named after the video stem. After the pipeline completes, both the video and its workspace are moved to `COMPLETED_DIR`:

```
COMPLETED_DIR/
  xd_Nhut JPzVyvsDungzPhong.mov        ← video file
  xd_Nhut JPzVyvsDungzPhong/           ← workspace (drop manual image here)
    metadata.json
    selected.jpg
    thumbnail.jpg
    upload.json
```

The `rethumbnail` command always operates on completed videos, so the workspace is always inside `COMPLETED_DIR`.

## Command Interface

```
uv run main.py rethumbnail <workspace>
```

`<workspace>` is either:
- A bare folder name (e.g., `"xd_Nhut JPzVyvsDungzPhong"`) — resolved against `COMPLETED_DIR`
- A full path to the workspace directory inside `COMPLETED_DIR`

## Flow

1. **Resolve workspace** — find the workspace directory inside `COMPLETED_DIR`
2. **Detect image** — scan workspace for `.jpg`/`.png` files excluding `thumbnail.jpg` and `selected.jpg`; pick the most recently modified; error if none found
3. **Replace `selected.jpg`** — copy detected image to `{workspace}/selected.jpg` (overwrite)
4. **Clear `thumbnail.jpg`** — delete existing render so the renderer does not skip
5. **Render** — call `render_thumbnail(video_path, template_name="template_b")`
6. **Set on YouTube** — call `set_thumbnail_for_video(video_path)` which reads `upload.json` for `video_id`

## Code Changes

### `utils.py`

Add alongside the existing `SUPPORTED_VIDEO_EXTENSIONS`:

```python
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".heic", ".heif"}
```

### New file: `rethumbnail.py`

Contains all logic extracted from `main.py` for testability:

```python
def find_manual_thumbnail(workspace_dir: Path) -> Path:
    """Scan workspace for newest non-reserved image file."""
    RESERVED = {SELECTED_CANDIDATE_NAME, RENDERED_THUMBNAIL_NAME}  # from utils.py
    candidates = [
        f for f in workspace_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS  # from utils.py
        and f.name not in RESERVED
    ]
    if not candidates:
        raise FileNotFoundError("No manual thumbnail image found in workspace")
    return max(candidates, key=lambda f: f.stat().st_mtime)

def rethumbnail_video(video_path: str) -> None:
    """Replace selected.jpg, re-render, and re-set YouTube thumbnail."""
    ...
```

### `main.py`

- Add `cmd_rethumbnail(args)` — resolves path, calls `rethumbnail_video()`
- Register `rethumbnail` subparser with `workspace` positional argument

## Error Cases

| Condition | Behaviour |
|---|---|
| Workspace not found in `COMPLETED_DIR` | Print clear error, exit non-zero |
| No eligible image in workspace | Print clear error, exit non-zero |
| `upload.json` missing or no `video_id` | Print clear error, exit non-zero |
| YouTube API failure | Surface API error message, exit non-zero |

## Testing

`tests/test_rethumbnail.py` covers `find_manual_thumbnail`:

- No images in workspace → raises `FileNotFoundError`
- Single valid image → returns it
- Multiple images → returns the most recently modified
- Only reserved names present → raises `FileNotFoundError`
- Mix of reserved and valid → returns valid one

`rethumbnail_video` integration test:
- Mocks `render_thumbnail` and `set_thumbnail_for_video`
- Verifies `selected.jpg` is replaced with detected image
- Verifies `thumbnail.jpg` is deleted before render is called

## Implementation Note: Path Resolution

`render_thumbnail` and `set_thumbnail_for_video` both call `get_workspace_dir(video_path)` which returns `INPUT_DIR / path.stem`. After cleanup, the workspace lives in `COMPLETED_DIR`, so passing the completed video path would resolve to the wrong directory.

`rethumbnail.py` will not use `get_workspace_dir`. Instead it will:
- Accept the `workspace_dir: Path` directly (resolved from the CLI argument)
- Read/write `selected.jpg` and `thumbnail.jpg` directly via `workspace_dir`
- Read `upload.json` directly via `workspace_dir / "upload.json"`
- Call `render_thumbnail` with a synthetic video path constructed as `COMPLETED_DIR / f"{workspace_dir.name}.mov"` if the high-level function is reused, OR call the template renderer at a lower level with explicit paths

The implementation plan will decide the exact approach (synthetic path vs. lower-level call), keeping changes minimal.

## Out of Scope

- Template selection (always `template_b`)
- Undo / backup of previous thumbnail
- Triggering via Temporal workflow signal
