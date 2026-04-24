## 1. Assets and utilities

- [x] 1.1 Download Anton-Regular.ttf from Google Fonts and place it in `assets/Anton-Regular.ttf`
- [x] 1.2 Add `PROCESSED_VIDEO_NAME = "processed.mov"` constant to `utils.py`
- [x] 1.3 Add `get_processed_video_path(video_path: Path) -> Path` function to `utils.py`
- [x] 1.4 Add `WORKFLOW_STAGE_ADDING_VIDEO_OVERLAYS = "ADDING_VIDEO_OVERLAYS"` to `constants.py`

## 2. video_overlay.py — overlay rendering

- [x] 2.1 Create `video_overlay.py` with `get_video_dimensions(video_path: str) -> tuple[int, int]` using ffprobe (returns width, height)
- [x] 2.2 Implement `render_cafe_game_overlay(width: int, height: int) -> Image` — renders CAFE in yellow with red drop shadow and halftone dots, GAME in white with red drop shadow and halftone dots, stacked and centered, using Anton-Regular font
- [x] 2.3 Implement `render_thanks_overlay(width: int, height: int) -> Image` — renders "THANKS FOR / WATCHING" in bold white Anton, rotated -10 degrees, centered
- [x] 2.4 Implement `add_video_overlays(video_path: str) -> str` — idempotency check, get dimensions, render both PNGs to temp files, run FFmpeg with hardware encoder (h264_videotoolbox fallback to libx264 ultrafast), return processed video path
- [x] 2.5 Handle short video guard: if duration <= 24s, skip the THANKS FOR WATCHING overlay

## 3. Temporal wiring

- [x] 3.1 Add `add_video_overlays_activity` to `temporal/activities.py` wrapping `add_video_overlays()`, raising non-retryable `ApplicationError` on `FileNotFoundError` (missing font)
- [x] 3.2 Import and register `add_video_overlays_activity` in `temporal/worker.py`
- [x] 3.3 Add `ADDING_VIDEO_OVERLAYS` stage to `temporal/workflows.py` between `ENHANCING_THUMBNAIL` and `UPLOADING`, with `start_to_close_timeout=timedelta(minutes=60)`

## 4. Upload path resolution

- [x] 4.1 Update `upload_video_activity` in `temporal/activities.py` to resolve the upload source: use `get_processed_video_path()` if it exists, otherwise fall back to original `video_path`

## 5. test-overlay CLI command

- [x] 5.1 Add `test-overlay` subcommand to `main.py` accepting `<input_video>` positional arg and optional `--output <path>` (default: `./overlay_test_output.mov`)
- [x] 5.2 Implement the command to call `video_overlay` internals directly with the given output path, bypassing workspace directory and idempotency check

## 6. Verification

- [x] 6.1 Run `uv run pytest` — confirm all existing tests pass
- [ ] 6.2 Run `uv run main.py test-overlay <sample.mov>` and open the output to visually verify CAFE GAME and THANKS FOR WATCHING styling
- [ ] 6.3 Verify idempotency: re-run the Temporal activity on the same video and confirm `processed.mov` is not overwritten
- [ ] 6.4 Confirm the upload activity picks up `processed.mov` rather than the original `.mov`

