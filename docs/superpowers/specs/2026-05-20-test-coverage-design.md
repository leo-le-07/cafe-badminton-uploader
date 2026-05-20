# Test Coverage Design

**Date:** 2026-05-20  
**Goal:** Improve test coverage from 43% to ~85%+ by covering all business logic. Skip: cv2 GUI (`display_gui_selection`), CLIP model loading (`clip_ranker.py`), Temporal workflows/activities, Flask web server, and `main.py` CLI.

---

## Approach

Module-by-module (Option B): write complete tests for one module at a time, ordered from easiest to hardest. Each module gets a dedicated test file. Mocking is limited to true 3rd-party boundaries.

---

## File Organization

| Test file | Source module |
|---|---|
| `tests/test_quality_filter.py` *(new)* | `thumbnail_ranking/quality_filter.py` |
| `tests/test_thumbnail_ranking_pipeline.py` *(new)* | `thumbnail_ranking/pipeline.py` |
| `tests/test_thumbnail_enhancement_common.py` *(new)* | `thumbnail_enhancement/common.py` |
| `tests/test_video_overlay.py` *(extend)* | `video_overlay.py` — rendering functions + ffprobe mocks |
| `tests/test_uploader.py` *(new)* | `uploader.py` |
| `tests/test_cleanup.py` *(new)* | `cleanup.py` |
| `tests/test_utils.py` *(new)* | `utils.py` |
| `tests/test_auth_service.py` *(extend)* | `auth_service.py` — OAuth paths |
| `tests/test_thumbnail_renderer.py` *(extend)* | `thumbnail_enhancement/renderer.py`, `template_a`, `template_b` |

---

## Testing Patterns

### Pure logic — no fixtures
Functions with no I/O or external calls are called directly:
- `passes_quality_check`, `filter_by_quality_thresholds`, `calculate_statistics`, `calculate_adaptive_thresholds`, `are_images_similar`, `remove_duplicate_images` (quality_filter)
- `get_theme_for_tournament`, `format_team_name`, `format_matchup_text` (common)
- `parse_channel_response` (auth_service)

### File I/O — real `tmp_path`
Use pytest's `tmp_path` fixture. Patch `config.INPUT_DIR` to point at the tmp dir so path helpers (`get_workspace_dir`, `get_metadata_path`, etc.) resolve correctly. Write real JSON/image files; assert on filesystem state and return values.

Applies to: `utils`, `cleanup`, `uploader` (save/load record, `get_videos_ready_for_upload`).

### Image operations — real PIL buffers
Create small (e.g. 320×180) `Image.new("RGB", ...)` objects with random or solid pixels. Run real PIL rendering code. Assert on output image size, mode, and that no exception is raised. Font files (`assets/Montserrat-ExtraBold.ttf`, `assets/Anton-Regular.ttf`) are loaded from disk — they exist in the repo.

Applies to: `enhance_image_visuals`, `add_logo` (common), `render_cafe_game_overlay`, `render_thanks_overlay`, template rendering.

### FFmpeg subprocess — patched `subprocess.run`
`patch("video_overlay.subprocess.run")` returning a `MagicMock` with `returncode=0` and `stdout` set to canned ffprobe JSON. Verify the command list structure where needed.

Applies to: `get_video_dimensions`, `_get_video_duration`.

### YouTube API — patched `get_client()`
`patch("uploader.get_client")` returning a `MagicMock`. Chain `.videos().insert().next_chunk()` etc. to return controlled responses. Assert that the correct API methods are called and that records are saved/read correctly.

Applies to: `upload`, `set_thumbnail_for_video`, `update_video_visibility_for_video`, `upload_video_with_idempotency`.

### OAuth — patched credentials + flow
`patch("auth_service.Credentials")` and `patch("auth_service.InstalledAppFlow")`. Test that `get_client()` raises when token file is missing, succeeds when present, and that `authenticate()` writes the token file.

### CLIP ranker — patched `rank_images`
`patch("thumbnail_ranking.pipeline.rank_images")` returning a list of fake `RankedImage` dataclasses. This keeps `rank_candidates` logic testable (directory checks, quality filter, dedup, file copy) without loading the ML model.

---

## Module-by-Module Test Coverage Plan

### 1. `thumbnail_ranking/quality_filter.py`
- `calculate_image_metrics`: pass a real tiny numpy array written to a temp JPEG; assert returned `ImageMetrics` fields are floats
- `collect_image_metrics_from_folder`: write 2 JPEGs to tmp dir; assert list length
- `passes_quality_check`: parametrize boundary conditions (each threshold)
- `filter_by_quality_thresholds`: list in, subset out
- `calculate_statistics`: assert all four metric keys present, correct percentile shape
- `calculate_adaptive_thresholds`: fixed stats dict in, assert `QualityThresholds` fields
- `are_images_similar`: two identical `ImageMetrics` (same phash) → similar; two very different phashes → not similar
- `remove_duplicate_images`: empty list, single item, duplicates removed, unique items kept

### 2. `thumbnail_ranking/pipeline.py`
- `rank_candidates`: missing candidates dir → `ValueError`; empty metrics → `ValueError`; all fail quality → `ValueError`; happy path with mocked `rank_images` → top N files copied to `top_candidates/`

### 3. `thumbnail_enhancement/common.py`
- `get_theme_for_tournament`: empty string → blue; "cafe game" → blue; "tournament" → purple; "Tour X" → purple; "friendly game" → white; unknown → blue
- `format_team_name`: single name, multiple names
- `format_matchup_text`: two teams → correct "vs" string
- `enhance_image_visuals`: real 320×180 RGB image in → RGB image same size out
- `add_logo`: logo missing → image returned unchanged; logo present (real `assets/logo.png`) → image returned

### 4. `video_overlay.py` (extend existing test file)
- `render_cafe_game_overlay`: real 1280×720 → RGBA image returned, same size
- `render_thanks_overlay`: same
- `_measure_text`: real font + draw → positive int tuple
- `_find_font_size_for_width`: converges to a size ≤ target width
- `get_video_dimensions`: mock ffprobe stdout → correct (width, height)
- `_get_video_duration`: mock ffprobe stdout → correct float
- `add_video_overlays` hardware fallback: first `subprocess.run` returns non-zero, second returns zero → result path returned
- `add_video_overlays` both fail → `RuntimeError`

### 5. `uploader.py`
- `save_upload_record`: writes JSON to tmp file; re-reading gives correct `UploadedRecord`; calling twice preserves original `uploaded_at`
- `get_videos_ready_for_upload`: skips paths with existing upload record; skips paths missing metadata or thumbnail; includes valid paths
- `upload_video_with_idempotency`: raises `VideoAlreadyUploadedError` when record with video_id exists; calls `upload()` and saves record on success (mock `get_client`)
- `set_thumbnail_for_video`: skips if `thumbnail_set=True`; raises if no upload record; calls `set_thumbnail` (mock `get_client`)
- `update_video_visibility_for_video`: raises if no upload record; calls API; raises on error response

### 6. `cleanup.py`
- `cleanup_video`: raises `NoUploadedRecordError` if no record; raises if workspace missing; happy path moves video file and workspace dir to `COMPLETED_DIR`

### 7. `utils.py`
- `scan_videos`: returns only `.mov`/`.MOV` files, ignores others
- `get_workspace_dir`, `get_candidate_dir`, etc.: pure path construction (parametrized)
- `get_metadata`: writes real JSON, reads back as `MatchMetadata`
- `get_uploaded_record`: returns `None` if file missing; returns `UploadedRecord` if present

### 8. `auth_service.py` (extend existing)
- `parse_channel_response`: valid response → `ChannelInfo`; missing items → `ValueError`; empty items → `ValueError`
- `get_client`: token file missing → `RuntimeError`; token present → mock `Credentials` + `build` called
- `authenticate`: mock flow writes token file → file exists after call

### 9. `thumbnail_enhancement/renderer.py`, `template_a`, `template_b` (extend existing)
- `get_template_module`: unknown name → `ValueError`; known names return modules
- `render_thumbnail` (renderer): skips if thumbnail already exists; calls template module on missing file
- `template_b.get_font`: font exists → `FreeTypeFont`; font missing → default font (no crash)
- `template_b.draw_sidebar_background`: real call → Image of correct size and color
- `template_a/b render_thumbnail`: write real selected.jpg + metadata JSON to tmp workspace; assert output thumbnail.jpg is created and is a valid JPEG

---

## What is Explicitly Skipped

| Code | Reason |
|---|---|
| `thumbnail_selector.display_gui_selection` | Requires cv2 GUI display |
| `thumbnail_ranking/clip_ranker.py` | Heavy ML model (CLIP); tested via pipeline mock |
| `temporal/workflows.py`, `temporal/activities.py` | Requires Temporal server |
| `temporal/client.py`, `temporal/worker.py` | Infrastructure; no business logic |
| `web_selector/server.py` | Flask UI server |
| `main.py` | CLI entry point |
