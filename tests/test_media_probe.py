import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from media_probe import SourceInfo, playback_path, probe


def ffprobe_result(payload: dict) -> MagicMock:
    return MagicMock(stdout=json.dumps(payload).encode(), returncode=0)


WITH_AUDIO_AND_TAGS = {
    "streams": [
        {
            "codec_type": "video",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30000/1001",
        },
        {"codec_type": "audio"},
    ],
    "format": {
        "duration": "61.5",
        "tags": {"creation_time": "2026-11-19T12:02:03.000000Z"},
    },
}

NO_AUDIO_NO_TAGS = {
    "streams": [
        {
            "codec_type": "video",
            "width": 1280,
            "height": 720,
            "r_frame_rate": "25/1",
        },
    ],
    "format": {"duration": "10"},
}


@pytest.fixture
def mock_run():
    with patch("media_probe.subprocess.run") as run:
        yield run


def test_probe_reads_streams_and_creation_time(mock_run, tmp_path):
    src = tmp_path / "a.mov"
    src.write_bytes(b"x")
    mock_run.return_value = ffprobe_result(WITH_AUDIO_AND_TAGS)

    info = probe(src)

    assert info.name == "a.mov"
    assert (info.width, info.height, info.has_audio) == (1920, 1080, True)
    assert info.fps == pytest.approx(29.97, abs=0.01)
    assert info.duration == 61.5
    assert info.recorded_at.startswith("2026-11-19")
    args = mock_run.call_args[0][0]
    assert args[0] == "ffprobe"
    assert str(src) in args


def test_probe_falls_back_to_mtime_and_detects_no_audio(mock_run, tmp_path):
    src = tmp_path / "b.mov"
    src.write_bytes(b"x")
    mtime = datetime(2026, 11, 18, 12, 0, 0).timestamp()
    os.utime(src, (mtime, mtime))
    mock_run.return_value = ffprobe_result(NO_AUDIO_NO_TAGS)

    info = probe(src)

    assert info.has_audio is False
    assert info.recorded_at.startswith("2026-11-18")
    assert info.fps == 25.0


def test_probe_caches_until_file_changes(mock_run, tmp_path):
    src = tmp_path / "c.mov"
    src.write_bytes(b"x")
    mock_run.return_value = ffprobe_result(NO_AUDIO_NO_TAGS)

    first = probe(src)
    second = probe(src)
    assert first == second
    assert mock_run.call_count == 1

    src.write_bytes(b"longer content")
    probe(src)
    assert mock_run.call_count == 2


def test_source_info_to_dict():
    info = SourceInfo(
        name="a.mov",
        duration=1.0,
        fps=30.0,
        width=1920,
        height=1080,
        has_audio=True,
        recorded_at="2026-11-19T19:02:03+07:00",
    )
    assert info.to_dict() == {
        "name": "a.mov",
        "duration": 1.0,
        "fps": 30.0,
        "width": 1920,
        "height": 1080,
        "has_audio": True,
        "recorded_at": "2026-11-19T19:02:03+07:00",
    }


def test_playback_path_is_the_source_itself(tmp_path):
    src = tmp_path / "a.mov"
    assert playback_path(src) == src


def _video_only(**video_fields) -> dict:
    video = {
        "codec_type": "video",
        "width": 1920,
        "height": 1080,
        "r_frame_rate": "30/1",
    }
    video.update(video_fields)
    return {"streams": [video], "format": {"duration": "10"}}


@pytest.mark.parametrize(
    "fields, expected",
    [
        (
            {"side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}]},
            (1080, 1920),
        ),
        ({"tags": {"rotate": "90"}}, (1080, 1920)),
        (
            {"side_data_list": [{"side_data_type": "Display Matrix", "rotation": 180}]},
            (1920, 1080),
        ),
        (
            {"side_data_list": [{"side_data_type": "Display Matrix", "rotation": 270}]},
            (1080, 1920),
        ),
        ({}, (1920, 1080)),
    ],
    ids=[
        "side-data-minus-90",
        "rotate-tag-90",
        "rotation-180",
        "rotation-270",
        "no-rotation",
    ],
)
def test_probe_reports_display_dimensions(mock_run, tmp_path, fields, expected):
    src = tmp_path / "r.mov"
    src.write_bytes(b"x")
    mock_run.return_value = ffprobe_result(_video_only(**fields))

    info = probe(src)

    assert (info.width, info.height) == expected


@pytest.mark.parametrize(
    "avg, r, expected",
    [
        ("30000/1001", "90000/1", 29.97),
        ("0/0", "30/1", 30.0),
        (None, "25/1", 25.0),
        ("garbage", "30/1", 30.0),
        ("0/0", "0/0", 0.0),
    ],
    ids=[
        "avg-preferred",
        "avg-zero",
        "avg-missing",
        "avg-unparseable",
        "both-unusable",
    ],
)
def test_probe_fps_prefers_avg_frame_rate(mock_run, tmp_path, avg, r, expected):
    src = tmp_path / "f.mov"
    src.write_bytes(b"x")
    fields = {"r_frame_rate": r}
    if avg is not None:
        fields["avg_frame_rate"] = avg
    mock_run.return_value = ffprobe_result(_video_only(**fields))

    assert probe(src).fps == pytest.approx(expected, abs=0.01)
