import cv2
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

from app.models import Segment
from video_prep import (
    score_frame,
    _extract_frame_at,
    sample_timestamps,
    select_thumbnail_from_segments,
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


# --- sample_timestamps tests ---


def test_sample_timestamps_stay_inside_kept_segments():
    segs = [Segment("a.mov", 10, 20), Segment("b.mov", 0, 30)]
    pts = sample_timestamps(segs, 8)
    assert len(pts) == 8
    for src, t in pts:
        assert (src == "a.mov" and 10 <= t <= 20) or (src == "b.mov" and 0 <= t <= 30)
    assert pts == sorted(pts, key=lambda p: (p[0] != "a.mov", p[1]))


def test_sample_timestamps_skip_first_and_last_ten_percent():
    # 40s kept in total: points span offsets 4..36 of the match
    segs = [Segment("a.mov", 10, 20), Segment("b.mov", 0, 30)]
    pts = sample_timestamps(segs, 3)
    assert pts == [
        ("a.mov", pytest.approx(14.0)),
        ("b.mov", pytest.approx(10.0)),
        ("b.mov", pytest.approx(26.0)),
    ]


def test_sample_timestamps_empty_segments():
    assert sample_timestamps([], 5) == []


# --- select_thumbnail_from_segments tests ---

SEGMENTS = [Segment("a.mov", 10, 20), Segment("b.mov", 0, 30)]


def test_select_thumbnail_from_segments_skips_if_output_exists(tmp_path):
    output = tmp_path / "selected.jpg"
    output.write_bytes(b"existing")

    with patch("video_prep._extract_frame_at") as mock_extract:
        select_thumbnail_from_segments(SEGMENTS, tmp_path, output)
        mock_extract.assert_not_called()

    assert output.read_bytes() == b"existing"


@patch("video_prep._extract_frame_at")
def test_select_thumbnail_from_segments_picks_sharpest(mock_extract, tmp_path):
    sharp_frame = make_checkerboard()
    dark_frame = make_frame(5)
    mock_extract.side_effect = [dark_frame, sharp_frame]
    output = tmp_path / "work" / "selected.jpg"

    with patch("video_prep.config.CANDIDATE_THUMBNAIL_NUM", 2):
        select_thumbnail_from_segments(SEGMENTS, tmp_path, output)

    assert output.exists()
    saved = cv2.imread(str(output))
    assert np.mean(saved) > 50
    called_paths = [c.args[0] for c in mock_extract.call_args_list]
    assert called_paths == [str(tmp_path / "a.mov"), str(tmp_path / "b.mov")]


@patch("video_prep._extract_frame_at")
def test_select_thumbnail_from_segments_raises_if_no_frames(mock_extract, tmp_path):
    mock_extract.return_value = None
    output = tmp_path / "selected.jpg"

    with patch("video_prep.config.CANDIDATE_THUMBNAIL_NUM", 3):
        with pytest.raises(ValueError, match="Could not extract"):
            select_thumbnail_from_segments(SEGMENTS, tmp_path, output)

    assert not output.exists()
