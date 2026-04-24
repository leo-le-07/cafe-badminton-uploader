## Why

Videos uploaded to YouTube currently start and end abruptly with raw game footage, missing branded framing. Adding a "CAFE GAME" intro overlay and "THANKS FOR WATCHING" outro overlay gives each video a consistent, professional identity without requiring manual post-production editing.

## What Changes

- New `video_overlay.py` module that renders two RGBA PNG overlays via Pillow (styled text on transparent background) and burns them into the video via a single FFmpeg pass
- New Temporal activity `add_video_overlays_activity` inserted between `ENHANCING_THUMBNAIL` and `UPLOADING` stages
- New workflow stage `ADDING_VIDEO_OVERLAYS` in `constants.py` and `workflows.py`
- `uploader.py` uses `processed.mov` from the workspace if it exists, falling back to the original video file
- `utils.py` gains `get_processed_video_path()` and `PROCESSED_VIDEO_NAME` constant
- Anton-Regular.ttf font bundled in `assets/` (bold condensed, matching the reference style)
- New `test-overlay` CLI command in `main.py` for quickly testing the overlay on any video without running the full Temporal workflow

## Capabilities

### New Capabilities

- `video-text-overlays`: Render styled "CAFE GAME" and "THANKS FOR WATCHING" text overlays onto video using Pillow + FFmpeg before upload

### Modified Capabilities

- `thumbnail-idempotency`: The idempotency pattern now extends to video processing — `processed.mov` is the skip-if-exists sentinel for the overlay step, and the upload step resolves the actual file path dynamically

## Impact

- **New dependency**: Anton-Regular.ttf must be present in `assets/` (user downloads from Google Fonts once)
- **Re-encoding required**: Full video re-encode via FFmpeg; uses macOS hardware encoder (`h264_videotoolbox`) by default with fallback to `libx264 -preset ultrafast`
- **Temporal timeout**: New activity needs 60-minute `start_to_close_timeout`
- **Upload path change**: `upload_video_activity` resolves which file to upload at runtime rather than always using the raw input path
- **No breaking changes** to the CLI interface or existing workflow signal/query API
