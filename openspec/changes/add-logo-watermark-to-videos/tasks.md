## 1. Config

- [x] 1.1 Add `LOGO_PATH` env var to `config.py` (default: `assets/logo.png`)

## 2. FFmpeg Integration

- [x] 2.1 Update `_run_ffmpeg_overlay` in `video_overlay.py` to accept a `logo_path` parameter and add the logo as an additional FFmpeg input
- [x] 2.2 Extend the `filter_complex` in `_run_ffmpeg_overlay` to scale the logo to 10% of video width (`scale=W*0.1:-1`) and overlay it at top-right (`x=main_w-overlay_w-20:y=20`) for the full duration, chained after the existing text overlay nodes
- [x] 2.3 Pass `format=rgba` on the logo input to preserve alpha transparency
- [x] 2.4 Update `add_video_overlays` in `video_overlay.py` to read `LOGO_PATH` from config and pass it to `_run_ffmpeg_overlay`

## 3. Tests

- [x] 3.1 Update existing `_run_ffmpeg_overlay` tests to cover the logo input parameter
- [x] 3.2 Add test verifying `add_video_overlays` skips re-encoding when `processed.mov` already exists (idempotency unchanged)
