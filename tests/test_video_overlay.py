import pytest
from PIL import Image, ImageDraw

from video_overlay import (
    RenderInput,
    build_render_command,
    _find_font_size_for_width,
    _get_font,
    _measure_text,
    INTRO_SLIDE_SECONDS,
    INTRO_STAGGER_SECONDS,
    THANKS_ZOOM_SECONDS,
    _thanks_text_block,
    render_cafe_game_words,
    overlay_timing,
    render_cafe_game_overlay,
    render_logo_badge,
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
        ["c.png"],
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
        ["c.png"],
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
        [_inp()], ["c.png"], None, 0, None, None, "o.mov", True, fps=30.0
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "[0:v]setpts=PTS-STARTPTS,scale=" in fc
    assert fc.index("setpts=PTS-STARTPTS") < fc.index("fps=30")
    assert "[0:a]asetpts=PTS-STARTPTS," in fc


def test_overlays_follow_concat_and_use_trimmed_time():
    cmd = build_render_command(
        [_inp(), _inp()], ["c.png"], "t.png", 18.0, "logo.png", 192, "o.mov", True
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert fc.index("concat=") < fc.index("overlay=")
    assert "enable='lte(t,12)'" in fc and "enable='gte(t,18.000)'" in fc
    assert "scale=192:-1" in fc


def test_audio_is_reencoded_not_copied():
    cmd = build_render_command([_inp()], ["c.png"], None, 0, None, None, "o.mov", True)
    assert cmd[cmd.index("-c:a") + 1] == "aac"
    assert cmd[cmd.index("-b:a") + 1] == "192k"


def test_segment_without_audio_gets_silence():
    cmd = build_render_command(
        [_inp(audio=False), _inp()], ["c.png"], None, 0, None, None, "o.mov", True
    )
    assert "anullsrc" in " ".join(cmd)


def test_mismatched_resolution_is_scaled_to_first_segment():
    cmd = build_render_command(
        [_inp(w=1920, h=1080), _inp(w=1280, h=720)],
        ["c.png"],
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
        ["c.png"],
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
    cmd = build_render_command([_inp()], ["c.png"], None, 0, None, None, "o.mov", True)
    assert "-hide_banner" in cmd


def test_encoder_choice():
    hw = build_render_command([_inp()], ["c.png"], None, 0, None, None, "o.mov", True)
    sw = build_render_command([_inp()], ["c.png"], None, 0, None, None, "o.mov", False)
    assert "h264_videotoolbox" in hw and "libx264" in sw


def test_no_logo_omits_logo_input_and_filter():
    cmd = build_render_command(
        [_inp()], ["c.png"], "t.png", 18.0, None, None, "o.mov", True
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "logo" not in " ".join(cmd)
    assert "[logo]" not in fc


def test_logo_is_top_right_watermark():
    cmd = build_render_command(
        [_inp()], ["c.png"], None, 0, "logo.png", 192, "o.mov", True
    )
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "main_w-overlay_w-20:y=20" in fc
    assert cmd[-1] == "o.mov"


def _thanks_command(fps=59.94):
    cmd = build_render_command(
        [_inp(), _inp()], ["c.png"], "t.png", 18.0, None, None, "o.mov", True, fps=fps
    )
    return cmd, cmd[cmd.index("-filter_complex") + 1]


def test_thanks_image_is_looped_for_the_outro_at_the_video_fps():
    cmd, _ = _thanks_command()
    j = " ".join(cmd)
    assert "-loop 1 -framerate 59.94 -t 12 -i t.png" in j
    # Unknown fps: the default.
    cmd, _ = _thanks_command(fps=None)
    assert "-loop 1 -framerate 30 -t 12 -i t.png" in " ".join(cmd)


def test_thanks_text_zooms_in_from_the_centre():
    _, fc = _thanks_command()
    # Scaled per frame on its own clock, then moved to start with the outro.
    assert "scale=w='" in fc and ":eval=frame" in fc
    assert f"t/{THANKS_ZOOM_SECONDS}" in fc
    assert "fade=t=in:st=0:" in fc and ":alpha=1" in fc
    assert fc.index("eval=frame") < fc.index("setpts=PTS+18.000/TB")
    assert "overlay=x=(W-w)/2:y=(H-h)/2:enable='gte(t,18.000)'" in fc


def test_intro_words_slide_in_one_after_another_and_back_out():
    cmd = build_render_command(
        [_inp()], ["cafe.png", "game.png"], None, 0, None, None, "o.mov", True
    )
    j = " ".join(cmd)
    fc = cmd[cmd.index("-filter_complex") + 1]
    # Plain single-frame inputs: nothing that could add frames to the video.
    assert "-i cafe.png -i game.png" in j and "-loop" not in j
    # Each word moves along x over time and is hidden after the intro.
    assert fc.count("overlay=x='") == 2
    assert fc.count("enable='lte(t,12)'") == 2
    # CAFE enters at once, GAME a moment later; they leave in the same order,
    # the last one off-screen when the intro ends.
    leave = 12 - INTRO_SLIDE_SECONDS - INTRO_STAGGER_SECONDS
    assert "(t-0)/" in fc and f"(t-{INTRO_STAGGER_SECONDS:g})/" in fc
    assert f"(t-{leave:g})/" in fc and f"(t-{leave + INTRO_STAGGER_SECONDS:g})/" in fc
    # CAFE is drawn first, GAME on top of it.
    assert fc.index("[1:v]") < fc.index("[2:v]")


class TestRenderCafeGameWords:
    def test_one_full_frame_image_per_word(self):
        words = render_cafe_game_words(1280, 720)
        assert len(words) == 2
        assert all(w.mode == "RGBA" and w.size == (1280, 720) for w in words)
        cafe, game = (w.getchannel("A").getbbox() for w in words)
        assert cafe[3] <= game[1] + 30  # CAFE sits above GAME
        assert cafe[0] < 1280 * 0.1 and game[0] < 1280 * 0.1  # left-aligned


class TestRenderLogoBadge:
    def _logo(self, tmp_path, size=(400, 400)):
        path = tmp_path / "logo.png"
        Image.new("RGBA", size, (255, 0, 0, 255)).save(path)
        return str(path)

    @pytest.mark.parametrize("logo_width", [128, 192, 384])
    def test_caption_sits_under_the_logo_without_clipping(self, tmp_path, logo_width):
        badge = render_logo_badge(self._logo(tmp_path), logo_width)
        assert badge.mode == "RGBA"
        assert badge.width >= logo_width
        assert badge.height > logo_width  # room for the caption below
        # The caption's pixels start under the logo and stay inside the badge.
        caption = badge.crop((0, logo_width, badge.width, badge.height))
        box = caption.getchannel("A").getbbox()
        assert box is not None
        assert box[0] > 0 and box[2] < badge.width
        assert box[3] < caption.height

    def test_logo_keeps_its_aspect_ratio(self, tmp_path):
        badge = render_logo_badge(self._logo(tmp_path, (400, 200)), 200)
        red = Image.new("RGBA", badge.size)
        red.putdata(
            [px if px[:3] == (255, 0, 0) else (0, 0, 0, 0) for px in badge.getdata()]
        )
        left, top, right, bottom = red.getchannel("A").getbbox()
        assert (right - left, bottom - top) == (200, 100)


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

    @pytest.mark.parametrize("width", [1280, 1920, 3840])
    def test_no_letter_is_cut_off(self, width):
        # The font's glyphs start well below y=0; text drawn without that
        # offset ran past the bottom of the block and lost its feet.
        block = _thanks_text_block(width)
        alpha = block.getchannel("A")
        w, h = block.size
        edges = [
            alpha.crop((0, 0, w, 2)),
            alpha.crop((0, h - 2, w, h)),
            alpha.crop((0, 0, 2, h)),
            alpha.crop((w - 2, 0, w, h)),
        ]
        assert all(edge.getbbox() is None for edge in edges)
        # Both lines are there: ink near the top and near the bottom.
        top, bottom = alpha.getbbox()[1], alpha.getbbox()[3]
        assert top < h * 0.15 and bottom > h * 0.85


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
