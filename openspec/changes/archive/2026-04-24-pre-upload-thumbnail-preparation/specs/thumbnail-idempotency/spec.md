## ADDED Requirements

### Requirement: Idempotent thumbnail selection
`auto_select_thumbnail(video_path)` SHALL skip frame extraction and scoring if `selected.jpg` already exists in the video's workspace directory, returning immediately without modifying any files.

#### Scenario: selected.jpg already exists
- **WHEN** `auto_select_thumbnail()` is called
- **AND** `selected.jpg` already exists in the workspace directory
- **THEN** the function returns immediately without invoking `ffprobe` or `ffmpeg`
- **THEN** `selected.jpg` is not overwritten

#### Scenario: selected.jpg does not exist
- **WHEN** `auto_select_thumbnail()` is called
- **AND** `selected.jpg` does not exist in the workspace directory
- **THEN** the function proceeds normally with frame extraction and scoring
- **THEN** the best frame is saved to `selected.jpg`

### Requirement: Idempotent thumbnail rendering
`render_thumbnail(video_path)` SHALL skip template rendering if `thumbnail.jpg` already exists in the video's workspace directory, returning immediately without modifying any files.

#### Scenario: thumbnail.jpg already exists
- **WHEN** `render_thumbnail()` is called
- **AND** `thumbnail.jpg` already exists in the workspace directory
- **THEN** the function returns immediately without invoking any template rendering
- **THEN** `thumbnail.jpg` is not overwritten

#### Scenario: thumbnail.jpg does not exist
- **WHEN** `render_thumbnail()` is called
- **AND** `thumbnail.jpg` does not exist in the workspace directory
- **THEN** the function proceeds normally with overlay rendering
- **THEN** the rendered image is saved to `thumbnail.jpg`

### Requirement: Temporal workflow replay safety
When a Temporal workflow replays after an upload failure, the thumbnail preparation stages SHALL not re-execute their expensive operations.

#### Scenario: Workflow replays after upload failure
- **WHEN** the `UPLOADING` activity fails and Temporal replays the workflow
- **THEN** `auto_select_thumbnail_activity` re-enters but exits early (selected.jpg exists)
- **THEN** `render_thumbnail_activity` re-enters but exits early (thumbnail.jpg exists)
- **THEN** only the upload activity performs meaningful work during the replay
