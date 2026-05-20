# Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tests to bring overall coverage from 43% to ~85%+ by covering all business logic across 9 source modules.

**Architecture:** Module-by-module approach — each source module gets a dedicated test file (new or extended). File I/O tests use real `tmp_path` fixtures with `monkeypatch.setattr(config, "INPUT_DIR", tmp_path)`. External calls (YouTube API, OAuth, FFmpeg) are mocked at the boundary. Image operations use real PIL buffers; fonts and logo exist at `assets/` and are loaded from disk.

**Tech Stack:** pytest, unittest.mock, PIL/Pillow, numpy, imagehash, cv2

---

### Task 1: quality_filter — pure logic tests

**Files:**
- Create: `tests/test_quality_filter.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_quality_filter.py
import numpy as np
import pytest
import imagehash
from PIL import Image

from thumbnail_ranking.quality_filter import (
    ImageMetrics,
    QualityThresholds,
    passes_quality_check,
    filter_by_quality_thresholds,
    calculate_statistics,
    calculate_adaptive_thresholds,
    are_images_similar,
    remove_duplicate_images,
)


def _make_metrics(
    phash="0000000000000000",
    brightness=150.0,
    contrast=50.0,
    sharpness=200.0,
    edge_density=0.1,
):
    return ImageMetrics(
        path="/fake/path.jpg",
        filename="path.jpg",
        brightness=brightness,
        contrast=contrast,
        sharpness=sharpness,
        edge_density=edge_density,
        phash=phash,
    )


def _phash_for(color: tuple) -> str:
    return str(imagehash.phash(Image.new("RGB", (64, 64), color)))


_THRESHOLDS = QualityThresholds(
    min_brightness=100,
    max_brightness=200,
    min_contrast=30,
    min_sharpness=100,
    min_edge_density=0.05,
)


class TestPassesQualityCheck:
    def test_passes_all_thresholds(self):
        m = _make_metrics(brightness=150, contrast=50, sharpness=200, edge_density=0.1)
        assert passes_quality_check(m, _THRESHOLDS) is True

    def test_fails_brightness_at_lower_bound(self):
        m = _make_metrics(brightness=100)  # not strictly greater than 100
        assert passes_quality_check(m, _THRESHOLDS) is False

    def test_fails_brightness_at_upper_bound(self):
        m = _make_metrics(brightness=200)  # not strictly less than 200
        assert passes_quality_check(m, _THRESHOLDS) is False

    def test_fails_contrast_at_bound(self):
        m = _make_metrics(brightness=150, contrast=30)  # not strictly greater than 30
        assert passes_quality_check(m, _THRESHOLDS) is False

    def test_fails_sharpness_at_bound(self):
        m = _make_metrics(brightness=150, contrast=50, sharpness=100)
        assert passes_quality_check(m, _THRESHOLDS) is False

    def test_fails_edge_density_at_bound(self):
        m = _make_metrics(brightness=150, contrast=50, sharpness=200, edge_density=0.05)
        assert passes_quality_check(m, _THRESHOLDS) is False


class TestFilterByQualityThresholds:
    def test_keeps_only_passing_metrics(self):
        good = _make_metrics(brightness=150, contrast=50, sharpness=200, edge_density=0.1)
        bad = _make_metrics(brightness=50)
        result = filter_by_quality_thresholds([good, bad], _THRESHOLDS)
        assert result == [good]

    def test_empty_list_returns_empty(self):
        assert filter_by_quality_thresholds([], _THRESHOLDS) == []

    def test_all_pass_returns_all(self):
        m1 = _make_metrics()
        m2 = _make_metrics(brightness=160)
        assert filter_by_quality_thresholds([m1, m2], _THRESHOLDS) == [m1, m2]


class TestCalculateStatistics:
    def test_returns_all_four_metric_keys(self):
        metrics = [_make_metrics()]
        stats = calculate_statistics(metrics)
        assert set(stats.keys()) == {"brightness", "contrast", "sharpness", "edge_density"}

    def test_percentiles_array_has_six_elements(self):
        metrics = [_make_metrics(), _make_metrics(brightness=160)]
        stats = calculate_statistics(metrics)
        for key in stats:
            assert stats[key].shape == (6,)

    def test_empty_list_returns_empty_dict(self):
        assert calculate_statistics([]) == {}


class TestCalculateAdaptiveThresholds:
    _STATS = {
        "brightness": np.array([80.0, 100.0, 130.0, 160.0, 175.0, 190.0]),
        "contrast": np.array([20.0, 35.0, 50.0, 65.0, 80.0, 90.0]),
        "sharpness": np.array([100.0, 150.0, 200.0, 250.0, 300.0, 350.0]),
        "edge_density": np.array([0.05, 0.08, 0.12, 0.16, 0.20, 0.25]),
    }

    def test_min_brightness_is_average_of_5th_and_25th_percentile(self):
        t = calculate_adaptive_thresholds(self._STATS)
        assert t.min_brightness == pytest.approx((80.0 + 100.0) / 2)

    def test_max_brightness_is_95th_percentile(self):
        t = calculate_adaptive_thresholds(self._STATS)
        assert t.max_brightness == pytest.approx(190.0)

    def test_min_contrast_is_25th_percentile(self):
        t = calculate_adaptive_thresholds(self._STATS)
        assert t.min_contrast == pytest.approx(35.0)

    def test_min_sharpness_is_25th_percentile(self):
        t = calculate_adaptive_thresholds(self._STATS)
        assert t.min_sharpness == pytest.approx(150.0)

    def test_min_edge_density_is_25th_percentile(self):
        t = calculate_adaptive_thresholds(self._STATS)
        assert t.min_edge_density == pytest.approx(0.08)

    def test_missing_keys_default_to_zero(self):
        t = calculate_adaptive_thresholds({})
        assert t.min_brightness == 0.0
        assert t.min_sharpness == 0.0


class TestAreImagesSimilar:
    def test_same_phash_is_similar(self):
        phash = _phash_for((128, 128, 128))
        m1 = _make_metrics(phash=phash)
        m2 = _make_metrics(phash=phash)
        assert are_images_similar(m1, m2, max_distance=8) is True

    def test_very_different_phashes_are_not_similar(self):
        m1 = _make_metrics(phash=_phash_for((0, 0, 0)))
        m2 = _make_metrics(phash=_phash_for((255, 255, 255)))
        assert are_images_similar(m1, m2, max_distance=8) is False


class TestRemoveDuplicateImages:
    def test_empty_list_returns_empty(self):
        assert remove_duplicate_images([], max_hash_distance=8) == []

    def test_single_item_returned_as_is(self):
        m = _make_metrics(phash=_phash_for((128, 128, 128)))
        assert remove_duplicate_images([m], max_hash_distance=8) == [m]

    def test_duplicate_phashes_deduplicated(self):
        phash = _phash_for((128, 128, 128))
        m1 = _make_metrics(phash=phash)
        m2 = _make_metrics(phash=phash)
        result = remove_duplicate_images([m1, m2], max_hash_distance=8)
        assert len(result) == 1
        assert result[0] is m1

    def test_distinct_images_both_kept(self):
        m1 = _make_metrics(phash=_phash_for((0, 0, 0)))
        m2 = _make_metrics(phash=_phash_for((255, 128, 0)))
        result = remove_duplicate_images([m1, m2], max_hash_distance=8)
        assert len(result) == 2


class TestImageMetricsHelpers:
    def test_to_dict_contains_all_fields(self):
        m = _make_metrics()
        d = m.to_dict()
        assert set(d.keys()) == {
            "path", "filename", "brightness", "contrast",
            "sharpness", "edge_density", "phash",
        }

    def test_get_phash_returns_imagehash_object(self):
        phash_str = _phash_for((100, 100, 100))
        m = _make_metrics(phash=phash_str)
        result = m.get_phash()
        assert isinstance(result, imagehash.ImageHash)
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_quality_filter.py -v
```

Expected: all tests PASS (no failures).

- [ ] **Step 3: Commit**

```bash
git add tests/test_quality_filter.py
git commit -m "test: add quality_filter pure logic tests"
```

---

### Task 2: quality_filter — image I/O tests

**Files:**
- Modify: `tests/test_quality_filter.py` (append)

- [ ] **Step 1: Append image I/O tests to the file**

Add these classes at the bottom of `tests/test_quality_filter.py`:

```python
from thumbnail_ranking.quality_filter import (
    calculate_image_metrics,
    collect_image_metrics_from_folder,
)
from pathlib import Path


def _make_striped_jpeg(path: Path, stripe_width: int = 4, size: int = 64) -> None:
    """Write a JPEG with alternating black/white rows — has edges and contrast."""
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for i in range(0, size, stripe_width * 2):
        arr[i:i + stripe_width, :] = 255
    Image.fromarray(arr).save(str(path), "JPEG", quality=95)


class TestCalculateImageMetrics:
    def test_returns_metrics_for_valid_jpeg(self, tmp_path):
        path = tmp_path / "frame.jpg"
        _make_striped_jpeg(path)
        metrics = calculate_image_metrics(path)
        assert metrics is not None
        assert isinstance(metrics.brightness, float)
        assert isinstance(metrics.contrast, float)
        assert isinstance(metrics.sharpness, float)
        assert isinstance(metrics.edge_density, float)
        assert isinstance(metrics.phash, str)
        assert metrics.filename == "frame.jpg"
        assert metrics.path == str(path)

    def test_returns_none_for_nonexistent_file(self, tmp_path):
        path = tmp_path / "missing.jpg"
        assert calculate_image_metrics(path) is None


class TestCollectImageMetricsFromFolder:
    def test_collects_metrics_for_all_jpegs(self, tmp_path):
        _make_striped_jpeg(tmp_path / "frame_001.jpg", stripe_width=2)
        _make_striped_jpeg(tmp_path / "frame_002.jpg", stripe_width=4)
        result = collect_image_metrics_from_folder(tmp_path)
        assert len(result) == 2

    def test_ignores_non_image_files(self, tmp_path):
        _make_striped_jpeg(tmp_path / "frame.jpg")
        (tmp_path / "notes.txt").write_text("hello")
        result = collect_image_metrics_from_folder(tmp_path)
        assert len(result) == 1

    def test_empty_folder_returns_empty_list(self, tmp_path):
        assert collect_image_metrics_from_folder(tmp_path) == []

    def test_results_sorted_by_filename(self, tmp_path):
        _make_striped_jpeg(tmp_path / "frame_002.jpg", stripe_width=4)
        _make_striped_jpeg(tmp_path / "frame_001.jpg", stripe_width=2)
        result = collect_image_metrics_from_folder(tmp_path)
        assert result[0].filename == "frame_001.jpg"
        assert result[1].filename == "frame_002.jpg"
```

Also update the imports block at the top of the file to include the new imports (`calculate_image_metrics`, `collect_image_metrics_from_folder`, `Path`). Add them to the existing import block:

```python
from pathlib import Path

from thumbnail_ranking.quality_filter import (
    ImageMetrics,
    QualityThresholds,
    calculate_image_metrics,
    collect_image_metrics_from_folder,
    passes_quality_check,
    filter_by_quality_thresholds,
    calculate_statistics,
    calculate_adaptive_thresholds,
    are_images_similar,
    remove_duplicate_images,
)
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_quality_filter.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_quality_filter.py
git commit -m "test: add quality_filter image I/O tests"
```

---

### Task 3: thumbnail_ranking pipeline tests

**Files:**
- Create: `tests/test_thumbnail_ranking_pipeline.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_thumbnail_ranking_pipeline.py
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

import config
from thumbnail_ranking.clip_ranker import RankedImage
from thumbnail_ranking.pipeline import rank_candidates
from thumbnail_ranking.quality_filter import ImageMetrics


def _make_striped_jpeg(path: Path, stripe_width: int = 4) -> None:
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    for i in range(0, 64, stripe_width * 2):
        arr[i:i + stripe_width, :] = 255
    Image.fromarray(arr).save(str(path), "JPEG", quality=95)


def _fake_ranked(path: str, rank: int = 1) -> RankedImage:
    metrics = ImageMetrics(
        path=path,
        filename=Path(path).name,
        brightness=150.0,
        contrast=50.0,
        sharpness=200.0,
        edge_density=0.1,
        phash="0000000000000000",
    )
    return RankedImage(metrics=metrics, clip_score=0.5, rank=rank)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    video = tmp_path / "ms_LeovsKhanh.mov"
    video.touch()
    candidates_dir = tmp_path / "ms_LeovsKhanh" / "candidates"
    candidates_dir.mkdir(parents=True)
    return video, candidates_dir


class TestRankCandidates:
    def test_raises_if_candidates_dir_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
        video = tmp_path / "ms_LeovsKhanh.mov"
        with pytest.raises(ValueError, match="Candidates directory does not exist"):
            rank_candidates(str(video))

    def test_raises_if_candidates_dir_is_empty(self, workspace):
        video, _ = workspace
        with pytest.raises(ValueError, match="No candidate images found"):
            rank_candidates(str(video))

    def test_raises_if_all_images_fail_quality(self, workspace):
        video, candidates_dir = workspace
        # Solid-colour images: sharpness ≈ 0, edge_density = 0 → fail quality even with adaptive thresholds
        Image.new("RGB", (64, 64), (128, 128, 128)).save(
            str(candidates_dir / "frame_001.jpg"), "JPEG"
        )
        Image.new("RGB", (64, 64), (130, 130, 130)).save(
            str(candidates_dir / "frame_002.jpg"), "JPEG"
        )
        with pytest.raises(ValueError, match="No candidates passed quality filtering"):
            rank_candidates(str(video))

    def test_happy_path_copies_top_n_files_to_top_candidates_dir(self, workspace):
        video, candidates_dir = workspace
        img1 = candidates_dir / "frame_001.jpg"
        img2 = candidates_dir / "frame_002.jpg"
        img3 = candidates_dir / "frame_003.jpg"
        _make_striped_jpeg(img1, stripe_width=2)
        _make_striped_jpeg(img2, stripe_width=6)
        _make_striped_jpeg(img3, stripe_width=10)

        ranked = [
            _fake_ranked(str(img1), rank=1),
            _fake_ranked(str(img2), rank=2),
        ]

        with patch("thumbnail_ranking.pipeline.rank_images", return_value=ranked):
            result = rank_candidates(str(video), top_n=2)

        top_dir = config.INPUT_DIR / "ms_LeovsKhanh" / "top_candidates"
        assert top_dir.exists()
        copied_files = list(top_dir.glob("*.jpg"))
        assert len(copied_files) == 2
        assert len(result) == 2

    def test_happy_path_respects_top_n_limit(self, workspace):
        video, candidates_dir = workspace
        for i, sw in enumerate([2, 4, 6, 8], start=1):
            _make_striped_jpeg(candidates_dir / f"frame_00{i}.jpg", stripe_width=sw)

        ranked = [_fake_ranked(str(candidates_dir / f"frame_00{i}.jpg"), rank=i) for i in range(1, 5)]

        with patch("thumbnail_ranking.pipeline.rank_images", return_value=ranked):
            result = rank_candidates(str(video), top_n=1)

        top_dir = config.INPUT_DIR / "ms_LeovsKhanh" / "top_candidates"
        assert len(list(top_dir.glob("*.jpg"))) == 1
        assert len(result) == 1
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_thumbnail_ranking_pipeline.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_thumbnail_ranking_pipeline.py
git commit -m "test: add thumbnail_ranking pipeline tests"
```

---

### Task 4: thumbnail_enhancement common tests

**Files:**
- Create: `tests/test_thumbnail_enhancement_common.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_thumbnail_enhancement_common.py
from pathlib import Path

import pytest
from PIL import Image

from thumbnail_enhancement.common import (
    STYLE_BLUE,
    STYLE_PURPLE,
    STYLE_WHITE,
    add_logo,
    enhance_image_visuals,
    format_matchup_text,
    format_team_name,
    get_theme_for_tournament,
)


class TestGetThemeForTournament:
    def test_empty_string_returns_blue(self):
        assert get_theme_for_tournament("") == STYLE_BLUE

    def test_cafe_game_returns_blue(self):
        assert get_theme_for_tournament("cafe game") == STYLE_BLUE

    def test_friendly_game_returns_white(self):
        assert get_theme_for_tournament("friendly game") == STYLE_WHITE

    def test_tournament_returns_purple(self):
        assert get_theme_for_tournament("tournament") == STYLE_PURPLE

    def test_tour_prefix_returns_purple(self):
        assert get_theme_for_tournament("Tour 2024") == STYLE_PURPLE

    def test_tournament_prefix_returns_purple(self):
        assert get_theme_for_tournament("Tournament Finals") == STYLE_PURPLE

    def test_unknown_name_returns_blue(self):
        assert get_theme_for_tournament("random league") == STYLE_BLUE

    def test_leading_and_trailing_whitespace_normalised(self):
        assert get_theme_for_tournament("  cafe game  ") == STYLE_BLUE


class TestFormatTeamName:
    def test_single_name_uppercased(self):
        assert format_team_name(["leo"]) == "LEO"

    def test_multiple_names_joined_by_slash_space(self):
        assert format_team_name(["den", "tu"]) == "DEN / TU"

    def test_already_uppercase_unchanged(self):
        assert format_team_name(["LEO"]) == "LEO"


class TestFormatMatchupText:
    def test_singles_matchup(self):
        assert format_matchup_text(["leo"], ["khanh"]) == "LEO vs KHANH"

    def test_doubles_matchup(self):
        assert format_matchup_text(["den", "tu"], ["huy", "ha"]) == "DEN / TU vs HUY / HA"


class TestEnhanceImageVisuals:
    def test_returns_rgb_image_of_same_size(self):
        img = Image.new("RGB", (320, 180), (100, 150, 200))
        result = enhance_image_visuals(img)
        assert result.mode == "RGB"
        assert result.size == (320, 180)

    def test_accepts_rgba_input(self):
        img = Image.new("RGBA", (320, 180), (100, 150, 200, 255))
        result = enhance_image_visuals(img)
        assert result.mode == "RGB"

    def test_accepts_greyscale_input(self):
        img = Image.new("L", (320, 180), 128).convert("RGB")
        result = enhance_image_visuals(img)
        assert result.mode == "RGB"


class TestAddLogo:
    def test_returns_image_unchanged_when_logo_missing(self, tmp_path):
        img = Image.new("RGB", (320, 180), (100, 150, 200))
        result = add_logo(img, tmp_path / "nonexistent.png")
        assert result.size == img.size

    def test_composites_real_logo_and_returns_image(self):
        img = Image.new("RGB", (320, 180), (100, 150, 200))
        result = add_logo(img, Path("assets/logo.png"))
        assert result.size == (320, 180)
        assert result.mode in ("RGB", "RGBA")
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_thumbnail_enhancement_common.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_thumbnail_enhancement_common.py
git commit -m "test: add thumbnail_enhancement common tests"
```

---

### Task 5: video_overlay — rendering and ffprobe tests

**Files:**
- Modify: `tests/test_video_overlay.py` (append new classes)

- [ ] **Step 1: Add imports and new test classes to the existing file**

Add these imports at the top of `tests/test_video_overlay.py` (after the existing imports):

```python
import json
from pathlib import Path
from PIL import Image, ImageDraw
```

Append these classes at the bottom of `tests/test_video_overlay.py`:

```python
from video_overlay import (
    _get_font,
    _get_video_duration,
    _measure_text,
    _find_font_size_for_width,
    get_video_dimensions,
    render_cafe_game_overlay,
    render_thanks_overlay,
)


class TestRenderCafeGameOverlay:
    def test_returns_rgba_image_of_requested_size(self):
        result = render_cafe_game_overlay(1280, 720)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGBA"
        assert result.size == (1280, 720)

    def test_raises_if_font_file_missing(self, tmp_path, monkeypatch):
        import video_overlay
        monkeypatch.setattr(video_overlay, "FONT_PATH", tmp_path / "missing.ttf")
        with pytest.raises(FileNotFoundError):
            render_cafe_game_overlay(1280, 720)


class TestRenderThanksOverlay:
    def test_returns_rgba_image_of_requested_size(self):
        result = render_thanks_overlay(1280, 720)
        assert isinstance(result, Image.Image)
        assert result.mode == "RGBA"
        assert result.size == (1280, 720)

    def test_raises_if_font_file_missing(self, tmp_path, monkeypatch):
        import video_overlay
        monkeypatch.setattr(video_overlay, "FONT_PATH", tmp_path / "missing.ttf")
        with pytest.raises(FileNotFoundError):
            render_thanks_overlay(1280, 720)


class TestMeasureText:
    def test_returns_positive_width_and_height(self):
        font = _get_font(30)
        canvas = Image.new("RGBA", (500, 200))
        draw = ImageDraw.Draw(canvas)
        w, h = _measure_text(draw, "CAFE", font)
        assert w > 0
        assert h > 0


class TestFindFontSizeForWidth:
    def test_chosen_font_fits_within_target_width(self):
        canvas = Image.new("RGBA", (1280, 720))
        draw = ImageDraw.Draw(canvas)
        target_width = 400
        size = _find_font_size_for_width(draw, "GAME", target_width)
        font = _get_font(size)
        w, _ = _measure_text(draw, "GAME", font)
        assert w <= target_width
        assert size > 0


class TestGetVideoDimensions:
    def test_parses_ffprobe_json_output(self):
        stdout = json.dumps({"streams": [{"width": 1920, "height": 1080}]}).encode()
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = stdout
        with patch("video_overlay.subprocess.run", return_value=mock_result):
            width, height = get_video_dimensions("video.mov")
        assert (width, height) == (1920, 1080)


class TestGetVideoDuration:
    def test_parses_ffprobe_duration_float(self):
        stdout = json.dumps({"format": {"duration": "3723.456"}}).encode()
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.stdout = stdout
        with patch("video_overlay.subprocess.run", return_value=mock_result):
            duration = _get_video_duration("video.mov")
        assert duration == pytest.approx(3723.456)


class TestAddVideoOverlaysFallback:
    def test_hardware_failure_falls_back_to_software_encoder(self, tmp_path, monkeypatch):
        import utils
        video = tmp_path / "match.mov"
        video.write_bytes(b"fake")
        output = tmp_path / "match_ws" / "processed.mov"

        fail = MagicMock(spec=subprocess.CompletedProcess, returncode=1, stderr=b"hw fail")
        success = MagicMock(spec=subprocess.CompletedProcess, returncode=0)

        with patch("video_overlay.get_video_dimensions", return_value=(1280, 720)), \
             patch("video_overlay._get_video_duration", return_value=30.0), \
             patch("utils.get_processed_video_path", return_value=output), \
             patch("video_overlay.subprocess.run", side_effect=[fail, success]):
            result = add_video_overlays(str(video))

        assert result == str(output)

    def test_both_encoders_fail_raises_runtime_error(self, tmp_path, monkeypatch):
        import utils
        video = tmp_path / "match.mov"
        video.write_bytes(b"fake")
        output = tmp_path / "match_ws" / "processed.mov"

        fail = MagicMock(spec=subprocess.CompletedProcess, returncode=1, stderr=b"fail")

        with patch("video_overlay.get_video_dimensions", return_value=(1280, 720)), \
             patch("video_overlay._get_video_duration", return_value=30.0), \
             patch("utils.get_processed_video_path", return_value=output), \
             patch("video_overlay.subprocess.run", return_value=fail):
            with pytest.raises(RuntimeError, match="FFmpeg failed"):
                add_video_overlays(str(video))
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_video_overlay.py -v
```

Expected: all tests PASS (existing 5 tests + new tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_video_overlay.py
git commit -m "test: add video_overlay rendering and ffprobe tests"
```

---

### Task 6: uploader tests

**Files:**
- Create: `tests/test_uploader.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_uploader.py
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import config
from schemas import MatchMetadata, UploadedRecord
from custom_exceptions import VideoAlreadyUploadedError
from uploader import (
    get_videos_ready_for_upload,
    save_upload_record,
    set_thumbnail_for_video,
    update_video_visibility_for_video,
    upload_video_with_idempotency,
)


_METADATA = MatchMetadata(
    match_type="Men's Singles",
    team1_names=["Leo"],
    team2_names=["Khanh"],
    tournament="Cafe Game",
    title="Leo vs Khanh | Cafe Game",
    description="Description",
    category="17",
)

_UPLOADED_RECORD = UploadedRecord(
    video_id="vid123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=False,
    youtube_link="https://youtu.be/vid123",
)


@pytest.fixture
def video_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    video = tmp_path / "ms_LeovsKhanh.mov"
    video.write_bytes(b"fake video content" * 100)
    workspace = tmp_path / "ms_LeovsKhanh"
    workspace.mkdir()
    (workspace / "metadata.json").write_text(
        json.dumps(asdict(_METADATA)), encoding="utf-8"
    )
    return video, workspace


class TestSaveUploadRecord:
    def test_writes_json_file(self, video_workspace):
        video, workspace = video_workspace
        save_upload_record(video, "vid123", thumbnail_set=False)
        upload_file = workspace / "upload.json"
        assert upload_file.exists()
        data = json.loads(upload_file.read_text())
        assert data["video_id"] == "vid123"
        assert data["thumbnail_set"] is False
        assert data["youtube_link"] == "https://youtu.be/vid123"

    def test_preserves_uploaded_at_on_second_write(self, video_workspace):
        video, workspace = video_workspace
        save_upload_record(video, "vid123", thumbnail_set=False)
        first_at = json.loads((workspace / "upload.json").read_text())["uploaded_at"]
        save_upload_record(video, "vid123", thumbnail_set=True)
        second_at = json.loads((workspace / "upload.json").read_text())["uploaded_at"]
        assert first_at == second_at

    def test_sets_thumbnail_set_true(self, video_workspace):
        video, _ = video_workspace
        save_upload_record(video, "vid123", thumbnail_set=True)
        from utils import get_uploaded_record
        record = get_uploaded_record(video)
        assert record is not None
        assert record.thumbnail_set is True


class TestGetVideosReadyForUpload:
    def test_excludes_path_with_existing_upload_record(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        save_upload_record(video, "vid123", thumbnail_set=False)
        result = get_videos_ready_for_upload([video])
        assert result == []

    def test_excludes_path_with_missing_metadata(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "metadata.json").unlink()
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        result = get_videos_ready_for_upload([video])
        assert result == []

    def test_excludes_path_with_missing_thumbnail(self, video_workspace):
        video, _ = video_workspace
        result = get_videos_ready_for_upload([video])
        assert result == []

    def test_includes_path_with_metadata_and_thumbnail(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        result = get_videos_ready_for_upload([video])
        assert result == [video]


class TestUploadVideoWithIdempotency:
    def test_raises_if_already_uploaded(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        with pytest.raises(VideoAlreadyUploadedError):
            upload_video_with_idempotency(str(video))

    def test_uploads_and_saves_record(self, video_workspace):
        video, workspace = video_workspace
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.insert.return_value.next_chunk.return_value = (
            None, {"id": "new_vid456"},
        )
        with patch("uploader.get_client", return_value=mock_youtube):
            result = upload_video_with_idempotency(str(video))
        assert result.video_id == "new_vid456"
        assert (workspace / "upload.json").exists()

    def test_uses_processed_video_if_it_exists(self, video_workspace):
        video, workspace = video_workspace
        processed = workspace / "processed.mov"
        processed.write_bytes(b"processed video" * 100)

        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.insert.return_value.next_chunk.return_value = (
            None, {"id": "proc_vid789"},
        )
        with patch("uploader.get_client", return_value=mock_youtube) as _, \
             patch("uploader.upload") as mock_upload:
            mock_upload.return_value = "proc_vid789"
            upload_video_with_idempotency(str(video))
            upload_path_used = mock_upload.call_args[0][1]
        assert upload_path_used == processed


class TestSetThumbnailForVideo:
    def test_raises_if_no_upload_record(self, video_workspace):
        video, _ = video_workspace
        with pytest.raises(RuntimeError, match="not uploaded"):
            set_thumbnail_for_video(str(video))

    def test_skips_if_thumbnail_already_set(self, video_workspace):
        video, workspace = video_workspace
        record = UploadedRecord(
            video_id="vid123", uploaded_at="2026-01-01T00:00:00",
            thumbnail_set=True, youtube_link="https://youtu.be/vid123",
        )
        (workspace / "upload.json").write_text(json.dumps(asdict(record)), encoding="utf-8")
        with patch("uploader.get_client") as mock_client:
            set_thumbnail_for_video(str(video))
            mock_client.assert_not_called()

    def test_sets_thumbnail_and_updates_record(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        (workspace / "thumbnail.jpg").write_bytes(b"img")

        mock_youtube = MagicMock()
        mock_youtube.thumbnails.return_value.set.return_value.execute.return_value = {}
        with patch("uploader.get_client", return_value=mock_youtube):
            set_thumbnail_for_video(str(video))

        from utils import get_uploaded_record
        record = get_uploaded_record(video)
        assert record is not None
        assert record.thumbnail_set is True


class TestUpdateVideoVisibilityForVideo:
    def test_raises_if_no_upload_record(self, video_workspace):
        video, _ = video_workspace
        with pytest.raises(RuntimeError, match="not uploaded"):
            update_video_visibility_for_video(str(video))

    def test_calls_videos_update(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.update.return_value.execute.return_value = {}
        with patch("uploader.get_client", return_value=mock_youtube):
            update_video_visibility_for_video(str(video))
        mock_youtube.videos.return_value.update.assert_called_once()

    def test_raises_on_error_response(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.update.return_value.execute.return_value = {
            "error": {"message": "Quota exceeded"}
        }
        with patch("uploader.get_client", return_value=mock_youtube):
            with pytest.raises(RuntimeError, match="Failed to update video visibility"):
                update_video_visibility_for_video(str(video))
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_uploader.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_uploader.py
git commit -m "test: add uploader tests"
```

---

### Task 7: cleanup tests

**Files:**
- Create: `tests/test_cleanup.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_cleanup.py
import json
from dataclasses import asdict
from pathlib import Path

import pytest

import config
from cleanup import cleanup_video
from custom_exceptions import NoUploadedRecordError
from schemas import UploadedRecord


_RECORD = UploadedRecord(
    video_id="vid123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=True,
    youtube_link="https://youtu.be/vid123",
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    (tmp_path / "completed").mkdir()

    video = tmp_path / "ms_LeovsKhanh.mov"
    video.write_bytes(b"video content")

    ws = tmp_path / "ms_LeovsKhanh"
    ws.mkdir()
    (ws / "upload.json").write_text(json.dumps(asdict(_RECORD)), encoding="utf-8")
    (ws / "thumbnail.jpg").write_bytes(b"img")

    return video, ws


class TestCleanupVideo:
    def test_raises_if_no_upload_record(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
        video = tmp_path / "ms_LeovsKhanh.mov"
        video.touch()
        (tmp_path / "ms_LeovsKhanh").mkdir()
        with pytest.raises(NoUploadedRecordError):
            cleanup_video(str(video))

    def test_raises_if_upload_record_has_no_video_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
        video = tmp_path / "ms_LeovsKhanh.mov"
        video.touch()
        ws = tmp_path / "ms_LeovsKhanh"
        ws.mkdir()
        empty_record = UploadedRecord(
            video_id="", uploaded_at="2026-01-01T00:00:00",
            thumbnail_set=False, youtube_link="",
        )
        (ws / "upload.json").write_text(json.dumps(asdict(empty_record)), encoding="utf-8")
        with pytest.raises(NoUploadedRecordError):
            cleanup_video(str(video))

    def test_raises_if_workspace_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
        video = tmp_path / "ms_LeovsKhanh.mov"
        video.touch()
        # No workspace dir created, and no upload record → raises
        with pytest.raises(NoUploadedRecordError):
            cleanup_video(str(video))

    def test_moves_video_and_workspace_to_completed(self, workspace):
        video, ws = workspace
        result = cleanup_video(str(video))
        completed = config.COMPLETED_DIR
        assert not video.exists()
        assert not ws.exists()
        assert (completed / video.name).exists()
        assert (completed / ws.name).exists()
        assert result == str(completed / video.name)
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_cleanup.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_cleanup.py
git commit -m "test: add cleanup tests"
```

---

### Task 8: utils tests

**Files:**
- Create: `tests/test_utils.py`

- [ ] **Step 1: Write the test file**

```python
# tests/test_utils.py
import json
from dataclasses import asdict
from pathlib import Path

import pytest

import config
from schemas import MatchMetadata, UploadedRecord
from utils import (
    SUPPORTED_VIDEO_EXTENSIONS,
    get_candidate_dir,
    get_metadata,
    get_metadata_path,
    get_processed_video_path,
    get_selected_candidate_path,
    get_thumbnail_path,
    get_top_ranked_candidates_dir,
    get_upload_record_path,
    get_uploaded_record,
    get_workspace_dir,
    scan_videos,
)


_METADATA = MatchMetadata(
    match_type="Men's Singles",
    team1_names=["Leo"],
    team2_names=["Khanh"],
    tournament="Cafe Game",
    title="Leo vs Khanh | Cafe Game",
    description="Description",
    category="17",
)

_RECORD = UploadedRecord(
    video_id="vid123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=False,
    youtube_link="https://youtu.be/vid123",
)


@pytest.fixture
def patched_input(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    return tmp_path


class TestScanVideos:
    def test_returns_only_mov_files(self, tmp_path):
        (tmp_path / "match.mov").touch()
        (tmp_path / "match.MOV").touch()
        (tmp_path / "match.mp4").touch()
        (tmp_path / "notes.txt").touch()
        results = list(scan_videos(tmp_path))
        suffixes = {p.suffix for p in results}
        assert suffixes == {".mov", ".MOV"}
        assert len(results) == 2

    def test_ignores_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "match.mov").touch()
        results = list(scan_videos(tmp_path))
        assert all(p.is_file() for p in results)

    def test_empty_directory_returns_empty(self, tmp_path):
        assert list(scan_videos(tmp_path)) == []


class TestPathHelpers:
    def test_get_workspace_dir(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        result = get_workspace_dir(video)
        assert result == patched_input / "ms_LeovsKhanh"

    def test_get_candidate_dir(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_candidate_dir(video) == patched_input / "ms_LeovsKhanh" / "candidates"

    def test_get_top_ranked_candidates_dir(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_top_ranked_candidates_dir(video) == patched_input / "ms_LeovsKhanh" / "top_candidates"

    def test_get_metadata_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_metadata_path(video) == patched_input / "ms_LeovsKhanh" / "metadata.json"

    def test_get_selected_candidate_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_selected_candidate_path(video) == patched_input / "ms_LeovsKhanh" / "selected.jpg"

    def test_get_thumbnail_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_thumbnail_path(video) == patched_input / "ms_LeovsKhanh" / "thumbnail.jpg"

    def test_get_processed_video_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_processed_video_path(video) == patched_input / "ms_LeovsKhanh" / "processed.mov"

    def test_get_upload_record_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_upload_record_path(video) == patched_input / "ms_LeovsKhanh" / "upload.json"


class TestGetMetadata:
    def test_reads_and_returns_match_metadata(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        ws = patched_input / "ms_LeovsKhanh"
        ws.mkdir()
        (ws / "metadata.json").write_text(
            json.dumps(asdict(_METADATA)), encoding="utf-8"
        )
        result = get_metadata(video)
        assert result.match_type == "Men's Singles"
        assert result.team1_names == ["Leo"]
        assert result.team2_names == ["Khanh"]


class TestGetUploadedRecord:
    def test_returns_none_when_file_missing(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        (patched_input / "ms_LeovsKhanh").mkdir()
        assert get_uploaded_record(video) is None

    def test_returns_upload_record_when_file_present(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        ws = patched_input / "ms_LeovsKhanh"
        ws.mkdir()
        (ws / "upload.json").write_text(
            json.dumps(asdict(_RECORD)), encoding="utf-8"
        )
        result = get_uploaded_record(video)
        assert result is not None
        assert result.video_id == "vid123"
        assert result.thumbnail_set is False
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_utils.py -v
```

Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_utils.py
git commit -m "test: add utils tests"
```

---

### Task 9: auth_service tests (extend existing)

**Files:**
- Modify: `tests/test_auth_service.py` (append)

- [ ] **Step 1: Append new tests to the existing file**

Add these imports at the top of `tests/test_auth_service.py` (after existing imports):

```python
from unittest.mock import patch, MagicMock
import auth_service
from auth_service import authenticate, get_client, parse_channel_response
from schemas import ChannelInfo
```

Append these classes at the bottom of `tests/test_auth_service.py`:

```python
class TestParseChannelResponse:
    def test_returns_channel_info_for_valid_response(self):
        response = {
            "items": [{
                "id": "UC123",
                "snippet": {"title": "Cafe Badminton", "description": "Videos"},
            }]
        }
        result = parse_channel_response(response)
        assert isinstance(result, ChannelInfo)
        assert result.channel_id == "UC123"
        assert result.title == "Cafe Badminton"
        assert result.description == "Videos"

    def test_raises_if_items_key_missing(self):
        with pytest.raises(ValueError, match="missing items"):
            parse_channel_response({})

    def test_raises_if_items_list_is_empty(self):
        with pytest.raises(ValueError, match="missing items"):
            parse_channel_response({"items": []})

    def test_description_defaults_to_empty_string(self):
        response = {
            "items": [{"id": "UC123", "snippet": {"title": "Chan"}}]
        }
        result = parse_channel_response(response)
        assert result.description == ""


class TestGetClient:
    def test_raises_if_token_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth_service, "TOKEN_FILE", str(tmp_path / "token.json"))
        with pytest.raises(RuntimeError, match="OAuth token not found"):
            get_client()

    def test_returns_youtube_client_when_token_exists(self, tmp_path, monkeypatch):
        token_file = tmp_path / "token.json"
        token_file.write_text('{"token": "fake"}')
        monkeypatch.setattr(auth_service, "TOKEN_FILE", str(token_file))

        mock_creds = MagicMock()
        mock_youtube = MagicMock()
        with patch("auth_service.Credentials.from_authorized_user_file", return_value=mock_creds), \
             patch("auth_service.build", return_value=mock_youtube):
            result = get_client()

        assert result is mock_youtube


class TestAuthenticate:
    def test_raises_if_client_secret_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth_service, "CLIENT_SECRET_FILE", str(tmp_path / "client_secret.json"))
        with pytest.raises(FileNotFoundError, match="Client secret file not found"):
            authenticate()

    def test_writes_token_file_on_success(self, tmp_path, monkeypatch):
        secret_file = tmp_path / "client_secret.json"
        secret_file.write_text("{}")
        token_file = tmp_path / "token.json"
        monkeypatch.setattr(auth_service, "CLIENT_SECRET_FILE", str(secret_file))
        monkeypatch.setattr(auth_service, "TOKEN_FILE", str(token_file))

        mock_creds = MagicMock()
        mock_creds.to_json.return_value = '{"access_token": "fake_token"}'
        mock_flow = MagicMock()
        mock_flow.run_local_server.return_value = mock_creds

        mock_youtube = MagicMock()
        mock_youtube.channels.return_value.list.return_value.execute.return_value = {
            "items": [{"id": "UC123", "snippet": {"title": "Chan", "description": ""}}]
        }

        with patch("auth_service.InstalledAppFlow.from_client_secrets_file", return_value=mock_flow), \
             patch("auth_service.build", return_value=mock_youtube):
            authenticate()

        assert token_file.exists()
        assert "access_token" in token_file.read_text()
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_auth_service.py -v
```

Expected: all tests PASS (existing 3 + new tests).

- [ ] **Step 3: Commit**

```bash
git add tests/test_auth_service.py
git commit -m "test: add auth_service parse, get_client, and authenticate tests"
```

---

### Task 10: thumbnail renderer and template tests

**Files:**
- Modify: `tests/test_thumbnail_renderer.py` (append)

- [ ] **Step 1: Append new tests to the existing file**

Add these imports at the top of `tests/test_thumbnail_renderer.py`:

```python
import json
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

import config
import thumbnail_enhancement.template_a as template_a
import thumbnail_enhancement.template_b as template_b
from thumbnail_enhancement.renderer import get_template_module
from schemas import MatchMetadata
```

Append these classes at the bottom of `tests/test_thumbnail_renderer.py`:

```python
_METADATA = MatchMetadata(
    match_type="Men's Singles",
    team1_names=["Leo"],
    team2_names=["Khanh"],
    tournament="Cafe Game",
    title="Leo vs Khanh | Cafe Game",
    description="Description",
    category="17",
)


@pytest.fixture
def template_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    video = tmp_path / "ms_LeovsKhanh.mov"
    video.touch()
    ws = tmp_path / "ms_LeovsKhanh"
    ws.mkdir()
    Image.new("RGB", (640, 360), (100, 150, 200)).save(
        str(ws / "selected.jpg"), "JPEG"
    )
    (ws / "metadata.json").write_text(
        json.dumps(asdict(_METADATA)), encoding="utf-8"
    )
    return video, ws


class TestGetTemplateModule:
    def test_returns_template_a_module(self):
        result = get_template_module("template_a")
        assert result is template_a

    def test_returns_template_b_module(self):
        result = get_template_module("template_b")
        assert result is template_b

    def test_raises_for_unknown_template_name(self):
        with pytest.raises(ValueError, match="Unknown template"):
            get_template_module("template_c")


class TestTemplateBGetFont:
    def test_returns_freetype_font_when_font_exists(self):
        from PIL.ImageFont import FreeTypeFont
        font = template_b.get_font(30)
        assert isinstance(font, FreeTypeFont)

    def test_returns_default_font_when_font_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(template_b, "FONT_PATH", tmp_path / "missing.ttf")
        font = template_b.get_font(30)
        assert font is not None  # load_default() never raises


class TestTemplateBDrawSidebarBackground:
    def test_returns_rgb_image_of_correct_size(self):
        sidebar = template_b.draw_sidebar_background(
            sidebar_w=576, canvas_h=1080, style_key="blue"
        )
        assert isinstance(sidebar, Image.Image)
        assert sidebar.size == (576, 1080)

    def test_blue_style_uses_deep_navy_background(self):
        sidebar = template_b.draw_sidebar_background(
            sidebar_w=100, canvas_h=100, style_key="blue"
        )
        r, g, b = sidebar.getpixel((50, 50))
        # Deep Navy: (0, 60, 150) — r should be very low
        assert r < 10


class TestTemplateARenderThumbnail:
    def test_creates_output_thumbnail_jpeg(self, template_workspace):
        video, ws = template_workspace
        result = template_a.render_thumbnail(video)
        thumbnail = ws / "thumbnail.jpg"
        assert thumbnail.exists()
        assert str(thumbnail) == result
        # Verify it's a valid JPEG
        img = Image.open(str(thumbnail))
        assert img.format == "JPEG"

    def test_raises_if_selected_jpg_missing(self, template_workspace):
        video, ws = template_workspace
        (ws / "selected.jpg").unlink()
        from custom_exceptions import MissingThumbnailDataError
        with pytest.raises(MissingThumbnailDataError):
            template_a.render_thumbnail(video)


class TestTemplateBRenderThumbnail:
    def test_creates_output_thumbnail_jpeg(self, template_workspace):
        video, ws = template_workspace
        result = template_b.render_thumbnail(video)
        thumbnail = ws / "thumbnail.jpg"
        assert thumbnail.exists()
        assert str(thumbnail) == result
        img = Image.open(str(thumbnail))
        assert img.format == "JPEG"

    def test_output_has_expected_canvas_size(self, template_workspace):
        video, ws = template_workspace
        template_b.render_thumbnail(video)
        img = Image.open(str(ws / "thumbnail.jpg"))
        assert img.size == (1920, 1080)

    def test_raises_if_selected_jpg_missing(self, template_workspace):
        video, ws = template_workspace
        (ws / "selected.jpg").unlink()
        from custom_exceptions import MissingThumbnailDataError
        with pytest.raises(MissingThumbnailDataError):
            template_b.render_thumbnail(video)
```

- [ ] **Step 2: Run and verify all tests pass**

```bash
uv run pytest tests/test_thumbnail_renderer.py -v
```

Expected: all tests PASS (existing 2 + new tests).

- [ ] **Step 3: Run the full test suite and check final coverage**

```bash
uv run pytest --cov=. -q 2>&1 | grep -E "(PASSED|FAILED|ERROR|coverage|TOTAL)"
```

Expected: all tests PASS, TOTAL coverage significantly above 43%.

- [ ] **Step 4: Commit**

```bash
git add tests/test_thumbnail_renderer.py
git commit -m "test: add thumbnail renderer and template A/B tests"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ quality_filter pure logic → Tasks 1–2
- ✅ pipeline.rank_candidates → Task 3
- ✅ common.py theme/format/PIL → Task 4
- ✅ video_overlay rendering + ffprobe + fallback → Task 5
- ✅ uploader save/load/upload/thumbnail/visibility → Task 6
- ✅ cleanup happy path + error paths → Task 7
- ✅ utils scan/path helpers/get_metadata/get_uploaded_record → Task 8
- ✅ auth_service parse/get_client/authenticate → Task 9
- ✅ renderer get_template_module + template_a/b render_thumbnail → Task 10
- ✅ Skipped: cv2 GUI, CLIP model, Temporal, Flask server, main.py CLI

**Type consistency:**
- `rank_candidates(video_path: str, top_n: int | None)` used correctly in Task 3
- `template_a.render_thumbnail(video_path: Path)` takes a Path — passed correctly from fixture
- `template_b.render_thumbnail(video_path: Path)` same
- `save_upload_record(video_path: Path, video_id: str, thumbnail_set: bool)` — first arg is Path; `video` from fixture is a Path ✅
- `UploadedRecord.video_id` is a str; `""` is falsy so empty string triggers `NoUploadedRecordError` ✅
