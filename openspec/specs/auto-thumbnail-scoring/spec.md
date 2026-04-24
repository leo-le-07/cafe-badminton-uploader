### Requirement: Frame scoring for thumbnail selection
`video_prep` SHALL expose an `auto_select_thumbnail(video_path)` function that uses FFmpeg subprocess calls to extract candidate frames directly into memory, scores each frame, and saves the highest-scoring frame as the selected thumbnail. No intermediate JPEG files are written to the candidates directory.

#### Scenario: Successful auto-selection
- **WHEN** `auto_select_thumbnail()` is called with a valid video path
- **THEN** the function invokes `ffprobe` to determine the video duration in seconds
- **THEN** candidate timestamps are computed as evenly spaced points across the middle 80% of the video duration
- **THEN** each candidate frame is extracted via `ffmpeg` fast input seeking and decoded in memory
- **THEN** each in-memory frame is scored on sharpness, brightness, and motion
- **THEN** the highest-scoring frame is saved to the selected candidate path
- **THEN** no JPEG files are written to the candidates workspace directory

#### Scenario: Frame scoring favours sharp, well-lit, active frames
- **WHEN** candidate frames include blurry, dark, and sharp/bright frames
- **THEN** the scoring algorithm assigns a higher composite score to sharp, well-lit frames with motion
- **THEN** the saved frame is not the blurriest or darkest candidate

#### Scenario: Skips intro and outro footage
- **WHEN** `auto_select_thumbnail()` is called
- **THEN** only frames from the middle 80% of the video (skipping first and last 10%) are considered

### ~~Requirement: `create_frame_candidates` disk extraction~~ (REMOVED)
**Reason**: The function wrote candidate frames to disk solely to support the now-removed web-based human selector. With auto-selection running in-memory via FFmpeg, disk-based extraction has no consumers and adds unnecessary I/O latency.
**Migration**: Remove calls to `create_frame_candidates`. Frame extraction is now internal to `auto_select_thumbnail`.

### Requirement: AUTO_SELECTING_THUMBNAIL workflow stage
`ProcessVideoWorkflow` SHALL include an `AUTO_SELECTING_THUMBNAIL` stage that runs before `UPLOADING`, after `CREATING_METADATA`.

#### Scenario: Thumbnail selection runs before upload
- **WHEN** the workflow starts processing a video
- **THEN** `auto_select_thumbnail_activity` executes after `create_metadata_activity`
- **THEN** `auto_select_thumbnail_activity` completes before `upload_video_activity` starts
- **THEN** `selected.jpg` exists in the workspace directory before upload begins

#### Scenario: Workflow progresses automatically through thumbnail selection
- **WHEN** the workflow reaches the thumbnail selection stage
- **THEN** `auto_select_thumbnail_activity` runs without any human signal or wait condition
- **THEN** the workflow advances to `ENHANCING_THUMBNAIL` immediately after the activity completes

#### Scenario: No blocking on human input
- **WHEN** multiple videos are being processed simultaneously
- **THEN** all workflows proceed through thumbnail selection without waiting for human interaction

### Requirement: Removal of human selection commands
The `list` and `select` CLI commands SHALL be removed as no workflows block waiting for human thumbnail selection.

#### Scenario: Pipeline runs end-to-end without human input
- **WHEN** `uv run main.py start` is executed
- **THEN** each video is processed fully automatically from upload to thumbnail set
- **THEN** no manual intervention is required at any stage
