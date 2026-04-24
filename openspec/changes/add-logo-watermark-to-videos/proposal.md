## Why

Videos uploaded to YouTube lack branding — adding the club logo as a watermark in the top-right corner establishes consistent brand identity across all published content. The logo asset already exists at `assets/logo.png`, making this a low-effort, high-visibility improvement.

## What Changes

- The existing `add_video_overlays` FFmpeg pass is extended to composite the logo in the same single encode, alongside the existing CAFE GAME and THANKS FOR WATCHING text overlays.
- No new workflow stage or activity is added — the logo is part of the existing `ADDING_VIDEO_OVERLAYS` step.
- The logo is scaled to ~10% of video width and placed 20px from the top-right corner, visible for the full video duration.

## Capabilities

### New Capabilities
*(none — logo compositing is folded into the existing `video-text-overlays` capability)*

### Modified Capabilities
- `video-overlays`: The `add_video_overlays` FFmpeg command is extended to include a permanent logo overlay in the top-right corner, composited in the same single pass as the existing text overlays.

## Impact

- `video_overlay.py` — `_run_ffmpeg_overlay` extended to accept an optional logo input and add it to the `filter_complex`; `add_video_overlays` passes the logo path and target size.
- `config.py` — `LOGO_PATH` env var added (default `assets/logo.png`).
- No new activities, workflow stages, or worker registrations needed.
- No schema changes; no new external dependencies (FFmpeg already used).
