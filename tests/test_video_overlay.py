import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from video_overlay import (
    _find_font_size_for_width,
    _get_font,
    _get_video_duration,
    _measure_text,
    _run_ffmpeg_overlay,
    add_video_overlays,
    get_video_dimensions,
    render_cafe_game_overlay,
    render_thanks_overlay,
)


def _make_result(returncode=0):
    r = MagicMock(spec=subprocess.CompletedProcess)
    r.returncode = returncode
    return r


class TestRunFfmpegOverlay:
    def test_logo_added_as_input_with_thanks(self):
        with patch("subprocess.run", return_value=_make_result()) as mock_run:
            _run_ffmpeg_overlay(
                "video.mp4",
                "cafe.png",
                "thanks.png",
                60.0,
                "out.mov",
                use_hardware=False,
                logo_path="logo.png",
                logo_size=192,
            )
            cmd = mock_run.call_args[0][0]
            assert "logo.png" in cmd
            assert cmd.index("logo.png") > cmd.index("thanks.png")

    def test_logo_added_as_input_without_thanks(self):
        with patch("subprocess.run", return_value=_make_result()) as mock_run:
            _run_ffmpeg_overlay(
                "video.mp4",
                "cafe.png",
                None,
                60.0,
                "out.mov",
                use_hardware=False,
                logo_path="logo.png",
                logo_size=192,
            )
            cmd = mock_run.call_args[0][0]
            assert "logo.png" in cmd

    def test_filter_complex_contains_logo_scale_and_overlay(self):
        with patch("subprocess.run", return_value=_make_result()) as mock_run:
            _run_ffmpeg_overlay(
                "video.mp4",
                "cafe.png",
                "thanks.png",
                60.0,
                "out.mov",
                use_hardware=False,
                logo_path="logo.png",
                logo_size=192,
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
                "video.mp4",
                "cafe.png",
                None,
                60.0,
                "out.mov",
                use_hardware=False,
            )
            cmd = mock_run.call_args[0][0]
            fc = cmd[cmd.index("-filter_complex") + 1]
            assert "scale=" not in fc
            assert "format=rgba" not in fc


class TestRenderCafeGameOverlay:
    def test_returns_rgba_image_of_correct_size(self):
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
    def test_returns_rgba_image_of_correct_size(self):
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
    def test_hardware_failure_falls_back_to_software_encoder(self, tmp_path):
        video = tmp_path / "match.mov"
        video.write_bytes(b"fake")
        output = tmp_path / "match_ws" / "processed.mov"

        fail = MagicMock(
            spec=subprocess.CompletedProcess, returncode=1, stderr=b"hw fail"
        )
        success = MagicMock(spec=subprocess.CompletedProcess, returncode=0)

        with (
            patch("video_overlay.get_video_dimensions", return_value=(1280, 720)),
            patch("video_overlay._get_video_duration", return_value=30.0),
            patch("utils.get_processed_video_path", return_value=output),
            patch("video_overlay.subprocess.run", side_effect=[fail, success]),
        ):
            result = add_video_overlays(str(video))

        assert result == str(output)

    def test_both_encoders_fail_raises_runtime_error(self, tmp_path):
        video = tmp_path / "match.mov"
        video.write_bytes(b"fake")
        output = tmp_path / "match_ws" / "processed.mov"

        fail = MagicMock(spec=subprocess.CompletedProcess, returncode=1, stderr=b"fail")

        with (
            patch("video_overlay.get_video_dimensions", return_value=(1280, 720)),
            patch("video_overlay._get_video_duration", return_value=30.0),
            patch("utils.get_processed_video_path", return_value=output),
            patch("video_overlay.subprocess.run", return_value=fail),
        ):
            with pytest.raises(RuntimeError, match="FFmpeg failed"):
                add_video_overlays(str(video))


class TestAddVideoOverlaysIdempotency:
    def test_skips_when_processed_already_exists(self, tmp_path):
        video = tmp_path / "match.mp4"
        video.touch()

        workspace = tmp_path / ".cafe_game_workspace" / "match"
        workspace.mkdir(parents=True)
        processed = workspace / "processed.mov"
        processed.touch()

        with (
            patch("video_overlay.get_video_dimensions"),
            patch("video_overlay._run_ffmpeg_overlay") as mock_ffmpeg,
            patch("utils.get_processed_video_path", return_value=processed),
        ):
            result = add_video_overlays(str(video))

        mock_ffmpeg.assert_not_called()
        assert result == str(processed)
