import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw

from video_overlay import (
    RenderInput,
    build_render_command,
    _find_font_size_for_width,
    _get_font,
    _get_video_duration,
    _measure_text,
    get_video_dimensions,
    overlay_timing,
    render_cafe_game_overlay,
    render_thanks_overlay,
)


def _inp(path="a.mov", s=10.0, e=25.0, audio=True, w=1920, h=1080, fps=30.0):
    return RenderInput(path, s, e, audio, w, h, fps)


def test_overlay_timing():
    assert overlay_timing(100.0) == (True, 88.0)
    assert overlay_timing(24.0) == (False, 12.0)


def test_each_segment_is_a_seeked_input():
    cmd = build_render_command(
        [_inp(s=10, e=25), _inp("b.mov", 0, 5.5)],
        "c.png",
        None,
        0,
        None,
        None,
        "o.mov",
        True,
    )
    j = " ".join(cmd)
    # Half a frame early (1/60 s at 30 fps), never before the file's start.
    assert "-ss 9.983333 -t 15.000000 -i a.mov" in j
    assert "-ss 0.000000 -t 5.500000 -i b.mov" in j
    assert "concat=n=2:v=1:a=1" in j


def test_seek_uses_each_segments_own_fps():
    cmd = build_render_command(
        [
            _inp(s=2 / 30, e=12 / 30, fps=30.0),
            _inp("b.mov", 2 * 1001 / 30000, 12 * 1001 / 30000, fps=30000 / 1001),
            _inp("c.mov", 1.0, 2.0, fps=0.0),
        ],
        "c.png",
        None,
        0,
        None,
        None,
        "o.mov",
        True,
    )
    j = " ".join(cmd)
    assert "-ss 0.050000 -t 0.333333 -i a.mov" in j
    assert "-ss 0.050050 -t 0.333667 -i b.mov" in j
    # Unknown fps falls back to 30.
    assert "-ss 0.983333 -t 1.000000 -i c.mov" in j


def test_timestamps_restart_before_fps_conversion():
    cmd = build_render_command(
        [_inp()], "c.png", None, 0, None, None, "o.mov", True, fps=30.0
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]setpts=PTS-STARTPTS,scale=" in fc
    assert fc.index("setpts=PTS-STARTPTS") < fc.index("fps=30")
    assert "[0:a]asetpts=PTS-STARTPTS," in fc


def test_overlays_follow_concat_and_use_trimmed_time():
    cmd = build_render_command(
        [_inp(), _inp()], "c.png", "t.png", 18.0, "logo.png", 192, "o.mov", True
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.index("concat=") < fc.index("overlay=")
    assert "enable='lte(t,12)'" in fc and "enable='gte(t,18.000)'" in fc
    assert "scale=192:-1" in fc


def test_audio_is_reencoded_not_copied():
    cmd = build_render_command([_inp()], "c.png", None, 0, None, None, "o.mov", True)
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-b:a") + 1] == "192k"


def test_segment_without_audio_gets_silence():
    cmd = build_render_command(
        [_inp(audio=False), _inp()], "c.png", None, 0, None, None, "o.mov", True
    )
    assert "anullsrc" in " ".join(cmd)


def test_mismatched_resolution_is_scaled_to_first_segment():
    cmd = build_render_command(
        [_inp(w=1920, h=1080), _inp(w=1280, h=720)],
        "c.png",
        None,
        0,
        None,
        None,
        "o.mov",
        True,
    )
    assert "scale=1920:1080" in cmd[cmd.index("-filter_complex") + 1]


def test_segments_are_converted_to_given_fps():
    cmd = build_render_command(
        [_inp(), _inp()],
        "c.png",
        None,
        0,
        None,
        None,
        "o.mov",
        True,
        fps=29.97002997002997,
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.count("fps=29.97002997") == 2


def test_banner_is_hidden():
    cmd = build_render_command([_inp()], "c.png", None, 0, None, None, "o.mov", True)
    assert "-hide_banner" in cmd


def test_encoder_choice():
    hw = build_render_command([_inp()], "c.png", None, 0, None, None, "o.mov", True)
    sw = build_render_command([_inp()], "c.png", None, 0, None, None, "o.mov", False)
    assert "h264_videotoolbox" in hw and "libx264" in sw


def test_no_logo_omits_logo_input_and_filter():
    cmd = build_render_command(
        [_inp()], "c.png", "t.png", 18.0, None, None, "o.mov", True
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "logo" not in " ".join(cmd)
    assert "format=rgba" not in fc


def test_logo_is_top_right_watermark():
    cmd = build_render_command(
        [_inp()], "c.png", None, 0, "logo.png", 192, "o.mov", True
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "main_w-overlay_w-20:y=20" in fc
    assert cmd[-1] == "o.mov"


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
