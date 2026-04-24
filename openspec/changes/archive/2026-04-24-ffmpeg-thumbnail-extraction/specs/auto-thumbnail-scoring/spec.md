## MODIFIED Requirements

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

## REMOVED Requirements

### Requirement: `create_frame_candidates` disk extraction
**Reason**: The function wrote candidate frames to disk solely to support the now-removed web-based human selector. With auto-selection running in-memory via FFmpeg, disk-based extraction has no consumers and adds unnecessary I/O latency.
**Migration**: Remove calls to `create_frame_candidates`. Frame extraction is now internal to `auto_select_thumbnail`.
