## Context

`auto_select_thumbnail_activity` currently takes 5+ minutes on 10-20 minute `.mov` videos. The bottleneck is OpenCV's `CAP_PROP_POS_FRAMES` seeking, which decodes from the nearest H.264/HEVC keyframe to each target frame for every one of the 10 seeks. Compounded over 10 seeks spread across a long video, this creates several minutes of unnecessary decode work.

Additionally, the current pipeline has a redundant disk round-trip: `create_frame_candidates` writes 10 full-resolution JPEG files to the `candidates/` workspace directory, then `auto_select_thumbnail` reads them all back for scoring. This was designed to support the now-removed web-based human selector.

## Goals / Non-Goals

**Goals:**
- Reduce `auto_select_thumbnail_activity` runtime from 5+ minutes to under 2 minutes
- Remove the redundant candidates-on-disk layer (no current consumers)
- Keep identical output: same scoring criteria, same selected thumbnail path

**Non-Goals:**
- Changing the sharpness/brightness/motion scoring weights
- Parallelising frame extraction across multiple videos
- Changing `CANDIDATE_THUMBNAIL_NUM` default (still configurable via env)
- GPU-accelerated decoding

## Decisions

### 1. Use FFmpeg subprocess with fast input seeking

Replace `cap.set(CAP_PROP_POS_FRAMES, idx)` with `ffmpeg -ss {seconds} -i {video} -vframes 1`.

Placing `-ss` *before* `-i` activates FFmpeg's container-level seeking: it reads the container's timestamp index and jumps to the nearest keyframe, then decodes only the few frames between that keyframe and the target timestamp. For H.264/HEVC this reduces per-frame extraction from 20-60 seconds to ~0.5-1 second.

**Alternatives considered:**
- `CAP_PROP_POS_MSEC` (time-based OpenCV seeking) — still decodes from the nearest keyframe; marginal improvement over frame-based seeking, same fundamental bottleneck
- `pyav` Python bindings — cleaner API, but adds a Python dependency that requires native FFmpeg libs; subprocess is simpler and sufficient

### 2. Use `ffprobe` for video duration

Get video duration in seconds via `ffprobe -v quiet -print_format json -show_format`, then compute target timestamps as `duration * fraction`. This is used instead of `cap.get(CAP_PROP_FRAME_COUNT)` which is unreliable for some `.mov` variants.

Frame timestamps (in seconds) replace frame indices as the unit for selecting candidates.

**Alternatives considered:**
- `cv2.CAP_PROP_FRAME_COUNT` + `CAP_PROP_FPS` — works for most files but flaky on `.mov` with VFR; `ffprobe` is the correct tool when FFmpeg is already required

### 3. In-memory pipeline — no intermediate JPEG files

Extract each frame from FFmpeg as raw bytes piped to stdout (`-f image2pipe -vcodec rawvideo` or JPEG via `-f singlejpeg`), decode in Python, score in memory, and discard. Only the winning frame is written to disk at the selected thumbnail path.

`create_frame_candidates` is removed entirely. `auto_select_thumbnail` becomes the single entry point handling extraction + scoring in one pass.

**Alternatives considered:**
- Keep `create_frame_candidates` writing to disk — adds measurable I/O overhead with no current benefit; the `candidates/` directory has no consumers since the web selector was removed
- Write a new version of `create_frame_candidates` that returns frames in memory — the name and original contract imply disk output; renaming/repurposing would be more confusing than removing

### 4. Pipe frames as JPEG via stdout

Use `ffmpeg -ss {t} -i {video} -vframes 1 -f image2 -vcodec mjpeg -q:v 2 pipe:1` and decode the raw JPEG bytes with `cv2.imdecode(np.frombuffer(stdout, np.uint8), cv2.IMREAD_COLOR)`.

This avoids temp files while keeping frames in a format OpenCV can decode. Quality `-q:v 2` is high enough for accurate sharpness scoring.

## Risks / Trade-offs

- **FFmpeg not installed** → `FileNotFoundError` at activity runtime. Mitigation: document `brew install ffmpeg` in README; optionally add a preflight check in the worker startup.
- **Very short videos (< 10 seconds)** → Timestamps may overlap or fall in the excluded 10%/90% window. Mitigation: existing `calculate_frame_indices`-equivalent logic already handles this; timestamps are clamped to the 10-90% window.
- **Corrupt or unsupported MOV variants** → FFmpeg has broader format support than OpenCV, so this is less of a risk than before. Errors surface as non-zero exit codes from the subprocess.
- **Motion scoring across non-consecutive seeks** → The current motion metric compares adjacent candidates which are not actually adjacent in the video. This is pre-existing behaviour and unchanged.

## Migration Plan

1. Install FFmpeg: `brew install ffmpeg` (local) or equivalent in CI/production
2. Deploy updated `video_prep.py`
3. Existing in-progress workflows that have already passed `AUTO_SELECTING_THUMBNAIL` are unaffected
4. The `candidates/` workspace directory will no longer be populated; existing workspace dirs with leftover candidate files are harmless
