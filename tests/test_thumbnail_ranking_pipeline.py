from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image

import config
from thumbnail_ranking.clip_ranker import RankedImage
from thumbnail_ranking.pipeline import rank_candidates
from thumbnail_ranking.quality_filter import ImageMetrics, QualityThresholds

_LENIENT_THRESHOLDS = QualityThresholds(
    min_brightness=0,
    max_brightness=300,
    min_contrast=0,
    min_sharpness=0,
    min_edge_density=0,
)


def _make_striped_jpeg(path: Path, stripe_width: int = 4) -> None:
    arr = np.zeros((64, 64, 3), dtype=np.uint8)
    for i in range(0, 64, stripe_width * 2):
        arr[i : i + stripe_width, :] = 255
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

        # Bypass adaptive thresholds (tested separately) so orchestration logic runs
        with (
            patch(
                "thumbnail_ranking.pipeline.calculate_adaptive_thresholds",
                return_value=_LENIENT_THRESHOLDS,
            ),
            patch("thumbnail_ranking.pipeline.rank_images", return_value=ranked),
        ):
            result = rank_candidates(str(video), top_n=2)

        top_dir = config.INPUT_DIR / "ms_LeovsKhanh" / "top_candidates"
        assert top_dir.exists()
        copied_files = list(top_dir.glob("*.jpg"))
        assert len(copied_files) == 2
        assert len(result) == 2

    def test_happy_path_respects_top_n_limit(self, workspace):
        video, candidates_dir = workspace
        imgs = []
        for i, sw in enumerate([2, 4, 6, 8], start=1):
            p = candidates_dir / f"frame_00{i}.jpg"
            _make_striped_jpeg(p, stripe_width=sw)
            imgs.append(p)

        ranked = [_fake_ranked(str(p), rank=i + 1) for i, p in enumerate(imgs)]

        with (
            patch(
                "thumbnail_ranking.pipeline.calculate_adaptive_thresholds",
                return_value=_LENIENT_THRESHOLDS,
            ),
            patch("thumbnail_ranking.pipeline.rank_images", return_value=ranked),
        ):
            result = rank_candidates(str(video), top_n=1)

        top_dir = config.INPUT_DIR / "ms_LeovsKhanh" / "top_candidates"
        assert len(list(top_dir.glob("*.jpg"))) == 1
        assert len(result) == 1
