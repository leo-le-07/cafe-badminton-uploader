## MODIFIED Requirements

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
