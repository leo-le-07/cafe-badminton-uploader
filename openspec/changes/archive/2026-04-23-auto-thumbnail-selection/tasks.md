## 1. Frame Scoring Algorithm

- [x] 1.1 Add `score_frame(frame, prev_frame)` to `video_prep.py` — returns composite score from sharpness (Laplacian variance), brightness (tent function), and motion (frame diff)
- [x] 1.2 Add `auto_select_thumbnail(video_path)` to `video_prep.py` — calls `create_frame_candidates()` to extract frames to disk, scores each loaded frame, saves highest-scoring frame to `get_selected_candidate_path()`

## 2. Temporal Wiring

- [x] 2.1 Add `WORKFLOW_STAGE_AUTO_SELECTING_THUMBNAIL` to `constants.py`; remove `WORKFLOW_STAGE_WAITING_FOR_SELECTION` and `WORKFLOW_STAGE_SELECTED`
- [x] 2.2 Add `auto_select_thumbnail_activity` to `temporal/activities.py`
- [x] 2.3 Register `auto_select_thumbnail_activity` in `temporal/worker.py`
- [x] 2.4 Update `ProcessVideoWorkflow` in `temporal/workflows.py`: remove `thumbnail_selected` signal, `wait_condition`, and old stages; add `AUTO_SELECTING_THUMBNAIL` stage calling the new activity

## 3. CLI Cleanup

- [x] 3.1 Remove `cmd_list` and `cmd_select` functions and their subparser registrations from `main.py`

## 4. Tests

- [x] 4.1 Add tests for `score_frame()` — verify sharpness, brightness, and motion signals score as expected
- [x] 4.2 Add tests for `auto_select_thumbnail()` — verify it picks the sharpest/best frame from a synthetic set and saves to the correct path
