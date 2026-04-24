import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from video_overlay import _run_ffmpeg_overlay, add_video_overlays


def _make_result(returncode=0):
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.returncode = returncode
    return r


class TestRunFfmpegOverlay:
    def test_logo_added_as_input_with_thanks(self):
        with patch("subprocess.run", return_value=_make_result()) as mock_run:
            _run_ffmpeg_overlay(
                "video.mp4", "cafe.png", "thanks.png", 60.0,
                "out.mov", use_hardware=False,
                logo_path="logo.png", logo_size=192,
            )
            cmd = mock_run.call_args[0][0]
            assert "logo.png" in cmd
            assert cmd.index("logo.png") > cmd.index("thanks.png")

    def test_logo_added_as_input_without_thanks(self):
        with patch("subprocess.run", return_value=_make_result()) as mock_run:
            _run_ffmpeg_overlay(
                "video.mp4", "cafe.png", None, 60.0,
                "out.mov", use_hardware=False,
                logo_path="logo.png", logo_size=192,
            )
            cmd = mock_run.call_args[0][0]
            assert "logo.png" in cmd

    def test_filter_complex_contains_logo_scale_and_overlay(self):
        with patch("subprocess.run", return_value=_make_result()) as mock_run:
            _run_ffmpeg_overlay(
                "video.mp4", "cafe.png", "thanks.png", 60.0,
                "out.mov", use_hardware=False,
                logo_path="logo.png", logo_size=192,
            )
            cmd = mock_run.call_args[0][0]
            fc = cmd[cmd.index("-filter_complex") + 1]
            assert "scale=192:-1" in fc
            assert "format=rgba" in fc
            assert "main_w-overlay_w-20" in fc
            assert "y=20" in fc

    def test_no_logo_omits_logo_from_filter(self):
        with patch("subprocess.run", return_value=_make_result()) as mock_run:
            _run_ffmpeg_overlay(
                "video.mp4", "cafe.png", None, 60.0,
                "out.mov", use_hardware=False,
            )
            cmd = mock_run.call_args[0][0]
            fc = cmd[cmd.index("-filter_complex") + 1]
            assert "scale=" not in fc
            assert "format=rgba" not in fc


class TestAddVideoOverlaysIdempotency:
    def test_skips_when_processed_already_exists(self, tmp_path):
        video = tmp_path / "match.mp4"
        video.touch()

        workspace = tmp_path / ".cafe_game_workspace" / "match"
        workspace.mkdir(parents=True)
        processed = workspace / "processed.mov"
        processed.touch()

        with patch("video_overlay.get_video_dimensions"), \
             patch("video_overlay._run_ffmpeg_overlay") as mock_ffmpeg, \
             patch("utils.get_processed_video_path", return_value=processed):
            result = add_video_overlays(str(video))

        mock_ffmpeg.assert_not_called()
        assert result == str(processed)
