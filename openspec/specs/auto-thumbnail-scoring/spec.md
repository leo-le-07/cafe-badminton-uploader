### Requirement: Frame scoring for thumbnail selection
`video_prep` SHALL expose an `auto_select_thumbnail(video_path)` function that uses `create_frame_candidates()` to extract frames to disk, scores each saved frame, and saves the highest-scoring frame as the selected thumbnail.

#### Scenario: Successful auto-selection
- **WHEN** `auto_select_thumbnail()` is called with a valid video path
- **THEN** the function calls `create_frame_candidates()` to extract frames to the candidates directory
- **THEN** each saved frame is loaded and scored on sharpness, brightness, and motion
- **THEN** the highest-scoring frame is saved to the selected candidate path

#### Scenario: Frame scoring favours sharp, well-lit, active frames
- **WHEN** candidate frames include blurry, dark, and sharp/bright frames
- **THEN** the scoring algorithm assigns a higher composite score to sharp, well-lit frames with motion
- **THEN** the saved frame is not the blurriest or darkest candidate

#### Scenario: Skips intro and outro footage
- **WHEN** `auto_select_thumbnail()` is called
- **THEN** only frames from the middle 80% of the video (skipping first and last 10%) are considered

### Requirement: AUTO_SELECTING_THUMBNAIL workflow stage
`ProcessVideoWorkflow` SHALL include an `AUTO_SELECTING_THUMBNAIL` stage that replaces `WAITING_FOR_SELECTION` and `SELECTED`.

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
