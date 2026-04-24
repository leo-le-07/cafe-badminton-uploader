import json
import subprocess
import cv2
import numpy as np
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from video_prep import (
    score_frame,
    _get_video_duration_seconds,
    _extract_frame_at,
    auto_select_thumbnail,
)


def make_frame(value: int) -> np.ndarray:
    return np.full((100, 100, 3), value, dtype=np.uint8)


def make_checkerboard() -> np.ndarray:
    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    frame[::2, ::2] = 255
    frame[1::2, 1::2] = 255
    return frame


def encode_jpeg(frame: np.ndarray) -> bytes:
    _, buf = cv2.imencode(".jpg", frame)
    return buf.tobytes()


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


# --- _get_video_duration_seconds tests ---

@patch("video_prep.subprocess.run")
def test_get_video_duration_seconds_returns_float(mock_run):
    payload = json.dumps({"format": {"duration": "923.456"}}).encode()
    mock_run.return_value = MagicMock(stdout=payload, returncode=0)

    result = _get_video_duration_seconds("video.mov")

    assert result == pytest.approx(923.456)
    args = mock_run.call_args[0][0]
    assert "ffprobe" in args
    assert "video.mov" in args


@patch("video_prep.subprocess.run")
def test_get_video_duration_seconds_raises_on_failure(mock_run):
    mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")

    with pytest.raises(subprocess.CalledProcessError):
        _get_video_duration_seconds("video.mov")


# --- _extract_frame_at tests ---

@patch("video_prep.subprocess.run")
def test_extract_frame_at_returns_frame(mock_run):
    jpeg_bytes = encode_jpeg(make_frame(128))
    mock_run.return_value = MagicMock(stdout=jpeg_bytes, returncode=0)

    result = _extract_frame_at("video.mov", 10.5)

    assert result is not None
    assert result.shape == (100, 100, 3)
    args = mock_run.call_args[0][0]
    assert "ffmpeg" in args
    assert "-ss" in args
    assert "10.500" in args


@patch("video_prep.subprocess.run")
def test_extract_frame_at_returns_none_on_ffmpeg_failure(mock_run):
    mock_run.return_value = MagicMock(stdout=b"", returncode=1)

    result = _extract_frame_at("video.mov", 10.5)

    assert result is None


@patch("video_prep.subprocess.run")
def test_extract_frame_at_uses_fast_seeking(mock_run):
    jpeg_bytes = encode_jpeg(make_frame(64))
    mock_run.return_value = MagicMock(stdout=jpeg_bytes, returncode=0)

    _extract_frame_at("video.mov", 30.0)

    args = mock_run.call_args[0][0]
    ss_index = args.index("-ss")
    i_index = args.index("-i")
    assert ss_index < i_index, "-ss must appear before -i for fast input seeking"


# --- auto_select_thumbnail tests ---

@patch("video_prep._extract_frame_at")
@patch("video_prep._get_video_duration_seconds")
def test_auto_select_thumbnail_saves_to_correct_path(mock_duration, mock_extract, tmp_path):
    mock_duration.return_value = 100.0
    mock_extract.return_value = make_checkerboard()

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()
    expected_output = tmp_path / "selected.jpg"

    with patch("video_prep.utils.get_selected_candidate_path", return_value=expected_output):
        auto_select_thumbnail(str(video_path))

    assert expected_output.exists()


@patch("video_prep._extract_frame_at")
@patch("video_prep._get_video_duration_seconds")
def test_auto_select_thumbnail_picks_sharpest_frame(mock_duration, mock_extract, tmp_path):
    mock_duration.return_value = 100.0
    sharp_frame = make_checkerboard()
    dark_frame = make_frame(5)
    mock_extract.side_effect = [dark_frame, sharp_frame]

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    saved_frames = []

    def fake_imwrite(path, frame):
        saved_frames.append(frame.copy())
        return True

    with patch("video_prep.utils.get_selected_candidate_path", return_value=tmp_path / "selected.jpg"):
        with patch("video_prep.cv2.imwrite", side_effect=fake_imwrite):
            with patch("video_prep.config.CANDIDATE_THUMBNAIL_NUM", 2):
                auto_select_thumbnail(str(video_path))

    assert len(saved_frames) == 1
    assert np.mean(saved_frames[0]) > 50


@patch("video_prep._extract_frame_at")
@patch("video_prep._get_video_duration_seconds")
def test_auto_select_thumbnail_raises_if_no_frames(mock_duration, mock_extract, tmp_path):
    mock_duration.return_value = 100.0
    mock_extract.return_value = None

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    with patch("video_prep.utils.get_selected_candidate_path", return_value=tmp_path / "selected.jpg"):
        with patch("video_prep.config.CANDIDATE_THUMBNAIL_NUM", 3):
            with pytest.raises(ValueError, match="Could not extract"):
                auto_select_thumbnail(str(video_path))
