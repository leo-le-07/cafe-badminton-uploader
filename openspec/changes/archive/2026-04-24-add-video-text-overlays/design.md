## Context

Each video currently uploads its raw `.mov` file directly to YouTube. The pipeline already produces per-video workspace directories (`INPUT_DIR/{stem}/`) holding metadata, thumbnail candidates, and the rendered thumbnail. Adding branded text overlays requires re-encoding the video before upload. The project uses FFmpeg (already on PATH for thumbnail frame extraction) and Pillow (already a dependency for thumbnail rendering).

Current stage order:
```
CREATING_METADATA → AUTO_SELECTING_THUMBNAIL → ENHANCING_THUMBNAIL → UPLOADING → UPDATING_VISIBILITY → SETTING_THUMBNAIL → COMPLETED
```

Target stage order:
```
CREATING_METADATA → AUTO_SELECTING_THUMBNAIL → ENHANCING_THUMBNAIL → ADDING_VIDEO_OVERLAYS → UPLOADING → …
```

## Goals / Non-Goals

**Goals:**
- Burn "CAFE GAME" text overlay onto frames 0–12s and "THANKS FOR WATCHING" onto the last 12s of every processed video
- Match the reference styling as closely as possible using Pillow compositing
- Keep the new stage idempotent (skip if `processed.mov` already exists)
- Use macOS hardware encoding for speed, with software fallback
- Upload the processed video instead of the original

**Non-Goals:**
- Animated or fade-in/out effects on the overlays
- Per-video configurable overlay text or duration (hardcoded for now)
- Changing the thumbnail pipeline or any stage after UPLOADING
- The `test-overlay` command participating in idempotency or workspace management (it is a dev tool only)

## Decisions

### D1: Pillow PNG → FFmpeg overlay (not pure FFmpeg drawtext)

**Decision:** Render overlay frames as RGBA PNGs using Pillow, then apply via FFmpeg `overlay` filter.

**Rationale:** The CAFE GAME style requires halftone dot patterns and per-word color fills — effects that FFmpeg's `drawtext` filter cannot produce. Pillow already handles complex image compositing for thumbnail rendering (`thumbnail_enhancement/`), making it the natural fit.

**Alternative considered:** Pure FFmpeg drawtext with stroke/shadow — achieves drop shadow and color but cannot produce halftone dot textures. Rejected.

### D2: Single FFmpeg pass with two overlay inputs

**Decision:** One FFmpeg invocation with two `-i overlay.png` inputs and a `filter_complex` chain, using `enable='lte(t,12)'` and `enable='gte(t,THANKS_START)'` timeline editing.

**Rationale:** Avoids intermediate segment files and concat complexity. `THANKS_START = duration - 12` is computed from ffprobe output before the FFmpeg call (reusing `_get_video_duration_seconds` from `video_prep.py`).

**Alternative considered:** Segment encode (re-encode only first/last 12s, stream-copy middle, then concat) — faster but produces encoding discontinuities at splice points and requires managing 3 temp files. Not worth the complexity for 12+12 = 24 seconds of overhead.

### D3: h264_videotoolbox default, libx264 fallback

**Decision:** Try `h264_videotoolbox` first; catch `FFmpegError` and retry with `libx264 -preset ultrafast`.

**Rationale:** Hardware encoding on macOS Apple Silicon completes a 2-hour 1080p video in ~2–4 min vs ~30–40 min for `-preset medium`. `-preset ultrafast` is the software fallback that stays within the 60-minute Temporal timeout even for very long recordings.

### D4: Upload resolves processed video path at runtime

**Decision:** `upload_video_activity` calls `get_processed_video_path(path)` and uploads that file if it exists, otherwise uploads the original `video_path`.

**Rationale:** Keeps the Temporal workflow signature unchanged (still passes `video_path` string to all activities). No new workflow inputs or return values needed.

### D5: Anton-Regular.ttf bundled in assets/

**Decision:** Ship the font file under `assets/Anton-Regular.ttf`. User downloads once from Google Fonts.

**Rationale:** Project already bundles `Montserrat-ExtraBold.ttf`. Anton is free (OFL), condensed, and visually close to Impact italic. Relying on system fonts (e.g., `/Library/Fonts/Impact.ttf`) is fragile across machines.

### D7: test-overlay command bypasses workspace and idempotency

**Decision:** `uv run main.py test-overlay <input> [--output <path>]` calls `add_video_overlays()` directly with a custom output path, skipping the workspace directory and idempotency check.

**Rationale:** The test command is a dev tool for visually validating overlay styling. It should work on any arbitrary video file and write to any output path, with no side effects on the workspace. Reusing `add_video_overlays()` internals (dimension detection, Pillow rendering, FFmpeg) means the test command exercises the exact same code path as the Temporal activity.

### D6: Overlay PNG resolution matches video resolution

**Decision:** Detect video width/height via ffprobe before rendering PNGs; render at that exact resolution.

**Rationale:** Avoids FFmpeg scaling the overlay, which could blur the carefully-composited text. Most recordings will be 1080p or 4K; detecting at runtime handles both.

## Risks / Trade-offs

- **Re-encode quality loss** → Mitigated: h264_videotoolbox at default quality is visually lossless for YouTube's subsequent re-encode. CRF tuning not needed.
- **h264_videotoolbox unavailable** (non-Mac or old macOS) → Mitigated: libx264 fallback in place; test for `returncode != 0` to detect encoder failure.
- **Font file missing** → `add_video_overlays_activity` raises `FileNotFoundError` at activity start, workflow fails with a clear message. No silent degradation.
- **Video shorter than 24s** → If `duration < 24`, the two overlays would overlap. Guard: if `duration <= 24`, skip the outro overlay (or center both). Spec covers this scenario.
- **Timeout for very long videos** → 60-minute Temporal timeout accommodates ~3-hour recordings with ultrafast fallback (~20 min encode). Extend if needed.

## Migration Plan

1. Worker picks up new activity automatically on restart — no Temporal namespace changes needed.
2. In-flight workflows that have already passed `ENHANCING_THUMBNAIL` will skip to `UPLOADING` as before (Temporal replays will add the new stage only for workflows that haven't reached it yet). Already-uploaded videos are protected by the `VideoAlreadyUploadedError` idempotency check.
3. `assets/Anton-Regular.ttf` must be present before the worker starts. Document in README.
