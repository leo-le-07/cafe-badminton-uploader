## 1. Idempotency Guards

- [x] 1.1 In `video_prep.py`, add an early-exit guard to `auto_select_thumbnail`: if `utils.get_selected_candidate_path(path)` exists, log and return immediately
- [x] 1.2 In `thumbnail_enhancement/renderer.py`, add an early-exit guard to `render_thumbnail`: if `utils.get_thumbnail_path(path)` exists, log and return immediately

## 2. Workflow Stage Reordering

- [x] 2.1 In `temporal/workflows.py`, move `AUTO_SELECTING_THUMBNAIL` and `ENHANCING_THUMBNAIL` activities to run after `CREATING_METADATA` and before `UPLOADING`

## 3. Documentation

- [x] 3.1 Update the workflow stage diagram in `CLAUDE.md` to reflect the new stage order

## 4. Tests

- [x] 4.1 Add a test for `auto_select_thumbnail` that verifies it skips when `selected.jpg` already exists
- [x] 4.2 Add a test for `render_thumbnail` that verifies it skips when `thumbnail.jpg` already exists
