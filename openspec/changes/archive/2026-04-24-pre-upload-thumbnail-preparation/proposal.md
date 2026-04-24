## Why

Thumbnail selection and rendering happen after upload today, meaning a ~120-minute upload must complete before thumbnail work begins. Moving these steps before upload allows thumbnail preparation to finish early, and ensures that if the upload fails and Temporal replays the workflow, the expensive thumbnail work is not repeated.

## What Changes

- Move `AUTO_SELECTING_THUMBNAIL` and `ENHANCING_THUMBNAIL` stages to run before `UPLOADING`
- Add idempotency guards to `auto_select_thumbnail` and `render_thumbnail`: skip if output files already exist on disk
- `SETTING_THUMBNAIL` remains after upload (requires YouTube video ID), but now consumes a pre-existing `thumbnail.jpg`
- Update workflow stage order in `workflows.py` and documentation

## Capabilities

### New Capabilities

- `thumbnail-idempotency`: Skip thumbnail selection and rendering if output files (`selected.jpg`, `thumbnail.jpg`) already exist in the workspace, making these activities safe to replay under Temporal workflow retries.

### Modified Capabilities

- `auto-thumbnail-scoring`: Execution point moves from post-upload to pre-upload; behavior is otherwise unchanged.

## Impact

- `temporal/workflows.py`: stage reordering
- `video_prep.py`: `auto_select_thumbnail` gains early-exit guard
- `thumbnail_enhancement/renderer.py` or its template modules: `render_thumbnail` gains early-exit guard
- `CLAUDE.md`: workflow stage diagram updated
