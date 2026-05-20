import numpy as np
import pytest
import imagehash
from pathlib import Path
from PIL import Image

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


def _make_striped_jpeg(path: Path, stripe_width: int = 4, size: int = 64) -> None:
    """Write a JPEG with alternating black/white rows — has edges and contrast."""
    arr = np.zeros((size, size, 3), dtype=np.uint8)
    for i in range(0, size, stripe_width * 2):
        arr[i : i + stripe_width, :] = 255
    Image.fromarray(arr).save(str(path), "JPEG", quality=95)


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
        good = _make_metrics(
            brightness=150, contrast=50, sharpness=200, edge_density=0.1
        )
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
        assert set(stats.keys()) == {
            "brightness",
            "contrast",
            "sharpness",
            "edge_density",
        }

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

    def test_different_phashes_are_not_similar_at_zero_distance(self):
        # Solid black and white have phash distance 1; with max_distance=0 they are not similar
        m1 = _make_metrics(phash=_phash_for((0, 0, 0)))
        m2 = _make_metrics(phash=_phash_for((255, 255, 255)))
        assert are_images_similar(m1, m2, max_distance=0) is False


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
        # max_distance=0 means only exact phash matches are deduplicated
        m1 = _make_metrics(phash=_phash_for((0, 0, 0)))
        m2 = _make_metrics(phash=_phash_for((255, 128, 0)))
        result = remove_duplicate_images([m1, m2], max_hash_distance=0)
        assert len(result) == 2


class TestImageMetricsHelpers:
    def test_to_dict_contains_all_fields(self):
        m = _make_metrics()
        d = m.to_dict()
        assert set(d.keys()) == {
            "path",
            "filename",
            "brightness",
            "contrast",
            "sharpness",
            "edge_density",
            "phash",
        }

    def test_get_phash_returns_imagehash_object(self):
        phash_str = _phash_for((100, 100, 100))
        m = _make_metrics(phash=phash_str)
        result = m.get_phash()
        assert isinstance(result, imagehash.ImageHash)


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
