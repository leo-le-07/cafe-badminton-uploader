## ADDED Requirements

### Requirement: CAFE GAME intro overlay
The system SHALL burn a "CAFE GAME" text overlay onto the first 12 seconds of every processed video. The overlay SHALL be centered on the frame with a transparent background so the underlying game footage remains visible.

#### Scenario: Normal video processing
- **WHEN** `add_video_overlays_activity` is called for a video
- **THEN** the first 12 seconds of the output video display the "CAFE GAME" text centered over the footage
- **THEN** the game footage underneath remains visible for the full duration

#### Scenario: Output file already exists (idempotent)
- **WHEN** `add_video_overlays_activity` is called
- **AND** `processed.mov` already exists in the workspace directory
- **THEN** the activity returns immediately without re-running FFmpeg

### Requirement: THANKS FOR WATCHING outro overlay
The system SHALL burn a "THANKS FOR WATCHING" text overlay onto the last 12 seconds of every processed video. The overlay SHALL be centered on the frame with a transparent background.

#### Scenario: Normal video processing
- **WHEN** `add_video_overlays_activity` is called for a video of duration D seconds
- **THEN** the "THANKS FOR WATCHING" overlay appears from second (D - 12) through second D
- **THEN** the game footage underneath remains visible during the outro

#### Scenario: Video shorter than 24 seconds
- **WHEN** the source video duration is 24 seconds or less
- **THEN** only the CAFE GAME intro overlay is applied (first 12s)
- **THEN** the THANKS FOR WATCHING overlay is skipped to avoid overlap

### Requirement: CAFE GAME text styling
The "CAFE GAME" overlay SHALL match the comic-book pop-art reference style as closely as possible using Pillow compositing.

#### Scenario: CAFE word rendering
- **WHEN** the CAFE GAME overlay PNG is rendered
- **THEN** "CAFE" is drawn in golden yellow (#FFD700) using Anton-Regular font at a large condensed size
- **THEN** a red (#CC0000) drop shadow is offset 8px right and 8px down behind "CAFE"
- **THEN** a halftone dot pattern (small red/orange circles on a grid) is composited over the "CAFE" text using the text shape as a mask

#### Scenario: GAME word rendering
- **WHEN** the CAFE GAME overlay PNG is rendered
- **THEN** "GAME" is drawn in white (#FFFFFF) using Anton-Regular font at a large condensed size
- **THEN** a red (#CC0000) drop shadow is offset 8px right and 8px down behind "GAME"
- **THEN** a halftone dot pattern (small pink/red circles on a grid) is composited over the "GAME" text using the text shape as a mask

#### Scenario: CAFE GAME layout
- **WHEN** the CAFE GAME overlay PNG is rendered
- **THEN** "CAFE" appears on the top line and "GAME" on the bottom line, stacked and horizontally centered
- **THEN** both words use a font size that fills roughly 60% of the frame width
- **THEN** the text block is vertically centered on the frame

### Requirement: THANKS FOR WATCHING text styling
The "THANKS FOR WATCHING" overlay SHALL match the bold white italic reference style.

#### Scenario: Text rendering
- **WHEN** the THANKS FOR WATCHING overlay PNG is rendered
- **THEN** the text is drawn in white (#FFFFFF) using Anton-Regular font at a large size
- **THEN** "THANKS FOR" appears on the first line and "WATCHING" on the second line
- **THEN** the entire text block is rotated approximately -10 degrees (counter-clockwise)
- **THEN** the rotated text block is centered on the frame

### Requirement: Hardware-accelerated encoding with software fallback
The system SHALL attempt macOS hardware encoding first and fall back to software encoding if unavailable.

#### Scenario: Hardware encoder available
- **WHEN** `add_video_overlays_activity` runs on macOS with h264_videotoolbox available
- **THEN** FFmpeg uses `-c:v h264_videotoolbox` for encoding

#### Scenario: Hardware encoder unavailable
- **WHEN** FFmpeg returns a non-zero exit code indicating h264_videotoolbox is unavailable
- **THEN** the system retries the FFmpeg command with `-c:v libx264 -preset ultrafast`
- **THEN** the activity succeeds using the software encoder

### Requirement: Font asset required
The system SHALL require `assets/Anton-Regular.ttf` to be present before video overlay processing can run.

#### Scenario: Font file missing
- **WHEN** `add_video_overlays_activity` is called
- **AND** `assets/Anton-Regular.ttf` does not exist
- **THEN** the activity raises `FileNotFoundError` with a clear message indicating the font path
- **THEN** the Temporal workflow fails with a non-retryable error

### Requirement: Upload uses processed video
The upload activity SHALL upload the processed video file when it exists in the workspace.

#### Scenario: Processed video exists
- **WHEN** `upload_video_activity` is called
- **AND** `processed.mov` exists in the workspace directory
- **THEN** the upload uses `processed.mov` as the source file

#### Scenario: Processed video does not exist
- **WHEN** `upload_video_activity` is called
- **AND** `processed.mov` does not exist in the workspace directory
- **THEN** the upload uses the original video path as the source file
