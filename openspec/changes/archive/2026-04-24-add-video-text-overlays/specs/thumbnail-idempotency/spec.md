## MODIFIED Requirements

### Requirement: Temporal workflow replay safety
When a Temporal workflow replays after an upload failure, the thumbnail preparation stages and video overlay stage SHALL not re-execute their expensive operations.

#### Scenario: Workflow replays after upload failure
- **WHEN** the `UPLOADING` activity fails and Temporal replays the workflow
- **THEN** `auto_select_thumbnail_activity` re-enters but exits early (selected.jpg exists)
- **THEN** `render_thumbnail_activity` re-enters but exits early (thumbnail.jpg exists)
- **THEN** `add_video_overlays_activity` re-enters but exits early (processed.mov exists)
- **THEN** only the upload activity performs meaningful work during the replay
