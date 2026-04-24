## Why

`auto_select_thumbnail_activity` takes over 5 minutes to complete because OpenCV's `CAP_PROP_POS_FRAMES` seeking decodes from the nearest keyframe to each target frame for every seek — on a 10-20 minute H.264/HEVC `.mov` file, 10 such seeks compound into several minutes of decode work. Reducing this to under 2 minutes requires replacing the seeking strategy.

## What Changes

- Replace OpenCV frame seeking in `create_frame_candidates` with `ffmpeg` subprocess calls using fast input seeking (`-ss` before `-i`), which jumps directly to the nearest container keyframe
- Merge frame extraction and scoring into a single in-memory pipeline — frames are scored and discarded without writing intermediate JPEG files to the candidates directory
- `create_frame_candidates` is removed; `auto_select_thumbnail` handles extraction + scoring in one pass
- Add `ffmpeg` as a required system dependency (installed via Homebrew or OS package manager, not a Python package)

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `auto-thumbnail-scoring`: Extraction changes from OpenCV disk-based seeking to FFmpeg in-memory extraction; `create_frame_candidates()` is no longer called and intermediate candidate JPEG files are no longer written to disk; the scoring algorithm (sharpness, brightness, motion) and output path are unchanged

## Impact

- `video_prep.py`: `create_frame_candidates` removed; `auto_select_thumbnail` rewritten
- `temporal/activities.py`: no change (same function signature)
- `tests/test_auto_thumbnail.py`: tests that mock `create_frame_candidates` need updating
- System dependency: `ffmpeg` must be installed in the environment
- `candidates/` workspace directory is no longer populated during auto-selection
