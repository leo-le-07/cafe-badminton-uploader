## Context

The `ProcessVideoWorkflow` in `temporal/workflows.py` runs these stages in order:
`CREATING_METADATA → UPLOADING → UPDATING_VISIBILITY → AUTO_SELECTING_THUMBNAIL → ENHANCING_THUMBNAIL → SETTING_THUMBNAIL → COMPLETED`

Upload can take up to 120 minutes. Thumbnail selection (`auto_select_thumbnail`) and rendering (`render_thumbnail`) only require the local video file — they have no dependency on the YouTube video ID produced by upload. Both write output files to the workspace directory (`selected.jpg`, `thumbnail.jpg`).

Temporal replays workflow history on retry: all activities before the failure point re-execute. Without idempotency guards, a failed upload causes thumbnail extraction and rendering to run again unnecessarily.

## Goals / Non-Goals

**Goals:**
- Move `AUTO_SELECTING_THUMBNAIL` and `ENHANCING_THUMBNAIL` before `UPLOADING`
- Make `auto_select_thumbnail` and `render_thumbnail` skip execution if their output files already exist
- `SETTING_THUMBNAIL` remains post-upload (requires video ID from `upload.json`)

**Non-Goals:**
- Changing thumbnail selection logic or scoring algorithm
- Changing retry/timeout configuration for any activity
- Adding new thumbnail templates or rendering options

## Decisions

**D1: Filesystem-as-checkpoint for idempotency**

Each thumbnail activity checks for its output file at the start and returns early if it exists. This avoids any new state management — the workspace directory already serves as the canonical state store for a video's processing progress.

Alternative considered: pass a `force` flag or add a workflow signal to re-run thumbnail steps. Rejected — adds complexity without a clear use case.

**D2: Reorder stages in `workflows.py` only — no new activities**

The reorder is a 4-line change in the workflow. No new activity types, no new signals, no schema changes.

**D3: Guard goes inside the activity function, not the workflow**

The skip logic belongs in `auto_select_thumbnail` (in `video_prep.py`) and `render_thumbnail` (in `thumbnail_enhancement/renderer.py`), not in the workflow. Activities should be self-idempotent; callers should not need to know about prior state.

## Risks / Trade-offs

**Stale thumbnail on re-run** → If a user deletes `selected.jpg` and `thumbnail.jpg` manually and re-triggers, a fresh thumbnail will be selected. This is the desired behavior; no mitigation needed.

**Thumbnail exists but is corrupt** → The guard checks file existence, not validity. A corrupt `thumbnail.jpg` would be silently reused. Mitigation: this is an edge case unlikely in normal operation; can be addressed later if it becomes a problem.

**Ordering dependency on `create_metadata_activity`** → `render_thumbnail` reads `metadata.json` to overlay player names. `CREATING_METADATA` already runs first, so this dependency is satisfied. No change needed.

## Migration Plan

No data migration. In-flight workflows at the time of deployment will be on the old stage order. Temporal replays based on recorded history, so existing workflows will complete on the old path. Only new workflows started after deployment use the new order.

Rollback: revert the stage order in `workflows.py` and remove the early-exit guards. No persistent state is affected.

## Open Questions

- None. The change is fully scoped.
