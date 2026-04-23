## Why

The current pipeline blocks at `WAITING_FOR_SELECTION`, requiring a human to manually scrub through each video and pick a thumbnail frame. Replacing this with automatic frame scoring removes the bottleneck and makes the pipeline fully hands-free.

## What Changes

- **BREAKING**: Remove `WAITING_FOR_SELECTION` and `SELECTED` workflow stages — the pipeline no longer pauses for human input
- **BREAKING**: Remove the `thumbnail_selected` signal and `wait_condition` from `ProcessVideoWorkflow`
- Add `AUTO_SELECTING_THUMBNAIL` workflow stage powered by a new `auto_select_thumbnail_activity`
- New frame scoring algorithm in `video_prep.py`: samples candidate frames, scores each by sharpness (Laplacian variance), brightness (histogram), and motion (frame differencing), saves the highest-scoring frame as the selected thumbnail
- Remove `cmd_list` and `cmd_select` CLI commands — no workflows will block waiting for selection
- `web_selector/` server is no longer part of the main workflow path

## Capabilities

### New Capabilities

- `auto-thumbnail-scoring`: Frame extraction and scoring algorithm that selects the best thumbnail candidate from a badminton match video

### Modified Capabilities

- `youtube-auth-validation`: No requirement changes — unaffected

## Impact

- `temporal/workflows.py`: Remove signal, wait_condition, two stages; add AUTO_SELECTING_THUMBNAIL stage
- `temporal/activities.py`: Add `auto_select_thumbnail_activity`; remove `select_thumbnail_web_activity`
- `video_prep.py`: Add `score_frame()` and `auto_select_thumbnail()` functions
- `constants.py`: Remove `WORKFLOW_STAGE_WAITING_FOR_SELECTION`, `WORKFLOW_STAGE_SELECTED`; add `WORKFLOW_STAGE_AUTO_SELECTING_THUMBNAIL`
- `main.py`: Remove `cmd_list`, `cmd_select` commands
- `web_selector/`: No longer invoked by the workflow (can remain as dead code or be removed)
