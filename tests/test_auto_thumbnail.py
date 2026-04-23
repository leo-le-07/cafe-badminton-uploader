import cv2
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from video_prep import score_frame, auto_select_thumbnail


def make_frame(value: int) -> np.ndarray:
    return np.full((100, 100, 3), value, dtype=np.uint8)


def make_checkerboard() -> np.ndarray:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[::2, ::2] = 255
    frame[1::2, 1::2] = 255
    return frame


# --- score_frame tests ---

def test_score_frame_sharp_beats_uniform():
    sharp = make_checkerboard()
    uniform = make_frame(128)
    assert score_frame(sharp)["sharpness"] > score_frame(uniform)["sharpness"]


def test_score_frame_brightness_peak_near_128():
    good = make_frame(128)
    dark = make_frame(5)
    bright = make_frame(250)
    assert score_frame(good)["brightness"] > score_frame(dark)["brightness"]
    assert score_frame(good)["brightness"] > score_frame(bright)["brightness"]


def test_score_frame_brightness_range():
    for value in [0, 64, 128, 192, 255]:
        scores = score_frame(make_frame(value))
        assert 0.0 <= scores["brightness"] <= 1.0


def test_score_frame_motion_with_prev():
    frame1 = make_frame(0)
    frame2 = make_frame(200)
    scores = score_frame(frame2, prev_frame=frame1)
    assert scores["motion"] > 0.0


def test_score_frame_no_motion_without_prev():
    scores = score_frame(make_frame(128))
    assert scores["motion"] == 0.0


def test_score_frame_no_motion_identical_frames():
    frame = make_frame(100)
    scores = score_frame(frame, prev_frame=frame)
    assert scores["motion"] == 0.0


# --- auto_select_thumbnail tests ---

def write_candidate(candidate_dir: Path, name: str, frame: np.ndarray) -> None:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(candidate_dir / name), frame)


@patch("video_prep.create_frame_candidates")
def test_auto_select_thumbnail_saves_to_correct_path(mock_create, tmp_path):
    candidate_dir = tmp_path / "candidates"
    sharp_frame = make_checkerboard()
    write_candidate(candidate_dir, "frame_000010.jpg", sharp_frame)

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    expected_output = tmp_path / "selected.jpg"
    with patch("video_prep.utils.get_candidate_dir", return_value=candidate_dir):
        with patch("video_prep.utils.get_selected_candidate_path", return_value=expected_output):
            auto_select_thumbnail(str(video_path))

    assert expected_output.exists()
    mock_create.assert_called_once_with(str(video_path))


@patch("video_prep.create_frame_candidates")
def test_auto_select_thumbnail_picks_sharpest_frame(mock_create, tmp_path):
    candidate_dir = tmp_path / "candidates"
    sharp_frame = make_checkerboard()
    dark_frame = make_frame(5)
    write_candidate(candidate_dir, "frame_000010.jpg", sharp_frame)
    write_candidate(candidate_dir, "frame_000020.jpg", dark_frame)

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    saved_frames = []

    def fake_imwrite(path, frame):
        saved_frames.append(frame.copy())
        return True

    with patch("video_prep.utils.get_candidate_dir", return_value=candidate_dir):
        with patch("video_prep.utils.get_selected_candidate_path", return_value=tmp_path / "selected.jpg"):
            with patch("video_prep.cv2.imwrite", side_effect=fake_imwrite):
                auto_select_thumbnail(str(video_path))

    assert len(saved_frames) == 1
    # sharp checkerboard (~128 mean) should be chosen over dark frame (5 mean)
    assert np.mean(saved_frames[0]) > 50


@patch("video_prep.create_frame_candidates")
def test_auto_select_thumbnail_raises_if_no_frames(mock_create, tmp_path):
    candidate_dir = tmp_path / "candidates"
    candidate_dir.mkdir()

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    with patch("video_prep.utils.get_candidate_dir", return_value=candidate_dir):
        with patch("video_prep.utils.get_selected_candidate_path", return_value=tmp_path / "selected.jpg"):
            with pytest.raises(ValueError, match="Could not extract"):
                auto_select_thumbnail(str(video_path))
