## Context

The pipeline produces a `processed.mov` per video via `add_video_overlays` in `video_overlay.py`. This function already builds a multi-input `filter_complex` for FFmpeg (CAFE GAME intro + THANKS FOR WATCHING outro). The logo asset at `assets/logo.png` has a transparent alpha channel and is circular.

Rather than adding a second encode pass, the logo is composited in the same FFmpeg invocation — one input added, one more `overlay` node in `filter_complex`.

## Goals / Non-Goals

**Goals:**
- Burn `assets/logo.png` into the top-right corner of every processed video with no extra encode pass.
- Keep the step idempotent: `processed.mov` existence check is unchanged.
- Preserve the hardware-encoder fallback pattern.

**Non-Goals:**
- Dynamic logo sizing or position configuration beyond a fixed margin.
- Animating or fading the logo.
- Applying the watermark to the thumbnail image.
- A separate workflow stage for the logo.

## Decisions

**1. Combine logo into the existing `_run_ffmpeg_overlay` pass**
Two separate FFmpeg re-encodes would double encoding time and introduce H.264 generation loss. A single pass with an extra input and overlay node is essentially free (no extra encode). Alternative (separate `add_logo_watermark_activity`) was rejected for these reasons.

**2. Logo as a permanent full-duration overlay (no `enable` time-gate)**
Text overlays are time-gated (`enable='lte(t,12)'`). The logo watermark should appear for the entire video, so no `enable` expression is needed.

**3. Logo size: scaled to 10% of video width via FFmpeg `scale` filter**
Using `scale=W*0.1:-1` (where `W` is the input video width) inside `filter_complex` scales the logo proportionally without needing Pillow. No Python-side size calculation required.

**4. Position: 20px from top-right using FFmpeg `overlay` `x`/`y` expressions**
`x=main_w-overlay_w-20:y=20` places the logo flush to the top-right corner with a 20px margin. This is a standard FFmpeg overlay expression.

**5. Alpha handling: `[logo]format=rgba` before overlay**
The logo PNG has an alpha channel. Passing it through `format=rgba` before the overlay ensures transparency compositing works correctly with both hardware and software encoders.

## Risks / Trade-offs

- **filter_complex complexity**: Adding a third input increases the chain length, but FFmpeg handles this reliably.
- **Logo transparency**: Verified visually — `assets/logo.png` has a true alpha background.
- **Workflow replay safety**: `processed.mov` existence check is unchanged; idempotency is preserved.

## Migration Plan

No new workflow stages. Existing in-progress workflows will re-run `ADDING_VIDEO_OVERLAYS` if `processed.mov` doesn't exist yet; if it does, the step is skipped. Already-uploaded videos are unaffected.
