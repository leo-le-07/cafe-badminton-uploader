## MODIFIED Requirements

### Requirement: Hardware-accelerated encoding with software fallback
The system SHALL attempt macOS hardware encoding first and fall back to software encoding if unavailable.

#### Scenario: Hardware encoder available
- **WHEN** `add_video_overlays_activity` runs on macOS with h264_videotoolbox available
- **THEN** FFmpeg uses `-c:v h264_videotoolbox` for encoding the combined output (text overlays + logo)

#### Scenario: Hardware encoder unavailable
- **WHEN** FFmpeg returns a non-zero exit code indicating h264_videotoolbox is unavailable
- **THEN** the system retries the FFmpeg command with `-c:v libx264 -preset ultrafast`
- **THEN** the activity succeeds using the software encoder

## ADDED Requirements

### Requirement: Logo watermark composited in the same FFmpeg pass
The system SHALL composite `assets/logo.png` (or the path from `LOGO_PATH` env var) into the top-right corner of the video within the same FFmpeg invocation as the text overlays, producing a single `processed.mov` output.

#### Scenario: Logo applied alongside text overlays
- **WHEN** `add_video_overlays_activity` is called for a video
- **THEN** the logo appears in the top-right corner for the full video duration
- **THEN** the CAFE GAME and THANKS FOR WATCHING text overlays are also present
- **THEN** only one `processed.mov` file is produced (no intermediate file)

#### Scenario: Output file already exists (idempotent)
- **WHEN** `add_video_overlays_activity` is called
- **AND** `processed.mov` already exists in the workspace directory
- **THEN** the activity returns immediately without re-running FFmpeg

### Requirement: Logo size and position
The logo SHALL be scaled to 10% of the video's width (preserving aspect ratio) and placed 20px from the top and right edges.

#### Scenario: Logo sizing via FFmpeg scale filter
- **WHEN** `add_video_overlays_activity` runs on a 1920×1080 video
- **THEN** the logo is scaled to approximately 192px wide using FFmpeg's `scale=W*0.1:-1` expression
- **THEN** the logo aspect ratio is preserved

#### Scenario: Logo position
- **WHEN** the watermark is applied
- **THEN** the logo's right edge is 20px from the right edge of the frame
- **THEN** the logo's top edge is 20px from the top edge of the frame

### Requirement: Logo transparency preserved
The logo's alpha channel SHALL be respected so the video content beneath remains visible.

#### Scenario: Transparent logo background
- **WHEN** `assets/logo.png` has an alpha channel
- **THEN** only the opaque pixels of the logo are composited onto the video
- **THEN** video content underneath the logo's transparent regions remains visible
