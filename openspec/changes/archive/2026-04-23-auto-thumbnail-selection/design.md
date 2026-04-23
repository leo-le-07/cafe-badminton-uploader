## Context

The current `ProcessVideoWorkflow` blocks at `WAITING_FOR_SELECTION` using Temporal's `wait_condition`, requiring a human to open a Flask web UI, scrub through the video, and click a frame. This makes the pipeline manual and non-scalable. The goal is to replace this with a fully automated frame scoring step that selects the best thumbnail without human input.

`create_frame_candidates()` already exists in `video_prep.py` and uses `cv2` to extract evenly-spaced frames. The new algorithm extends this with per-frame quality scoring.

## Goals / Non-Goals

**Goals:**
- Fully automated thumbnail selection with no workflow pause
- Frame scoring tailored to badminton match content (active play, sharp, well-lit)
- No new dependencies — use `cv2` and `numpy` already in the project

**Non-Goals:**
- Human review or override path (removed entirely)
- ML-based player/shuttle detection
- Keeping `web_selector/` active in the main workflow path

## Decisions

**Score frames on three signals, pick the highest composite score**

Each candidate frame is scored 0–1 on:
1. **Sharpness** — Laplacian variance normalized across candidates. Filters out motion-blurred frames.
2. **Brightness** — Penalizes frames too dark (<40 mean) or too bright (>220 mean) using a tent function peaked at ~128.
3. **Motion** — Absolute frame difference vs. the previous sampled frame, normalized. Prefers active rally moments over static serves or dead ball.

Composite score = weighted average (sharpness 0.4, brightness 0.3, motion 0.3). Weights favour sharpness since blurry frames are visually worst for thumbnails.

Alternative considered: inline frame extraction (reading directly from `VideoCapture` in `auto_select_thumbnail`) — rejected in favour of reusing `create_frame_candidates`, which already handles uniform sampling and writes candidates to disk. This keeps extraction and scoring as separate, independently testable concerns.

Alternative considered: ML pose estimation (MediaPipe) to detect jump smashes — rejected as overkill; adds a heavy dependency for marginal gain over the signal-based approach.

**Skip first and last 10% of the video**

Badminton match recordings typically start with camera setup and end with post-match chatter. Scoring only the middle 80% avoids picking a thumbnail from non-game footage.

**`auto_select_thumbnail` delegates extraction to `create_frame_candidates`**

`auto_select_thumbnail()` calls `create_frame_candidates()` first to extract and save frames to the candidates directory, then loads those files from disk and scores them. This separates extraction from scoring: `create_frame_candidates` owns the cv2/VideoCapture work; `auto_select_thumbnail` owns the scoring logic. Each is independently testable. `auto_select_thumbnail_activity` in `activities.py` wraps the whole thing as a Temporal activity, mirroring the existing `create_metadata` / `create_metadata_activity` pattern.

**Selected frame saved to the same path as before**

The enhancer (`render_thumbnail_activity`) reads from `get_selected_candidate_path(video_path)`. The auto-select step writes to the same path — no changes needed downstream.

## Risks / Trade-offs

- [Algorithm picks a suboptimal frame] → Acceptable trade-off for full automation; frame quality is "good enough" even if not perfect
- [First/last 10% skip misses a genuinely good frame in a short clip] → Low probability; most match recordings are long enough that 80% has many good candidates
- [Removing human step is irreversible per workflow run] → User accepts this; the old path is removed intentionally
