import json
from dataclasses import asdict
from unittest.mock import patch

import pytest
from PIL import Image

import config
import thumbnail_enhancement.template_a as template_a
import thumbnail_enhancement.template_b as template_b
from custom_exceptions import MissingThumbnailDataError
from schemas import MatchMetadata
from thumbnail_enhancement.renderer import get_template_module, render_thumbnail

_METADATA = MatchMetadata(
    match_type="Men's Singles",
    team1_names=["Leo"],
    team2_names=["Khanh"],
    tournament="Cafe Game",
    title="Leo vs Khanh | Cafe Game",
    description="Description",
    category="17",
)


@pytest.fixture
def template_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    video = tmp_path / "ms_LeovsKhanh.mov"
    video.touch()
    ws = tmp_path / "ms_LeovsKhanh"
    ws.mkdir()
    Image.new("RGB", (640, 360), (100, 150, 200)).save(str(ws / "selected.jpg"), "JPEG")
    (ws / "metadata.json").write_text(json.dumps(asdict(_METADATA)), encoding="utf-8")
    return video, ws


def test_render_thumbnail_skips_if_thumbnail_jpg_exists(tmp_path):
    thumbnail = tmp_path / "thumbnail.jpg"
    thumbnail.write_bytes(b"existing")

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    with patch(
        "thumbnail_enhancement.renderer.utils.get_thumbnail_path",
        return_value=thumbnail,
    ):
        with patch(
            "thumbnail_enhancement.renderer.get_template_module"
        ) as mock_get_template:
            result = render_thumbnail(str(video_path))
            mock_get_template.assert_not_called()

    assert result == str(thumbnail)
    assert thumbnail.read_bytes() == b"existing"


def test_render_thumbnail_proceeds_if_thumbnail_jpg_missing(tmp_path):
    thumbnail = tmp_path / "thumbnail.jpg"

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    mock_template = patch("thumbnail_enhancement.renderer.get_template_module")
    mock_path = patch(
        "thumbnail_enhancement.renderer.utils.get_thumbnail_path",
        return_value=thumbnail,
    )

    with mock_path, mock_template as mock_get_template:
        mock_get_template.return_value.render_thumbnail.return_value = str(thumbnail)
        render_thumbnail(str(video_path))
        mock_get_template.assert_called_once()


class TestGetTemplateModule:
    def test_returns_template_a_module(self):
        result = get_template_module("template_a")
        assert result is template_a

    def test_returns_template_b_module(self):
        result = get_template_module("template_b")
        assert result is template_b

    def test_raises_for_unknown_template_name(self):
        with pytest.raises(ValueError, match="Unknown template"):
            get_template_module("template_c")


class TestTemplateBGetFont:
    def test_returns_freetype_font_when_font_exists(self):
        from PIL.ImageFont import FreeTypeFont

        font = template_b.get_font(30)
        assert isinstance(font, FreeTypeFont)

    def test_returns_default_font_when_font_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(template_b, "FONT_PATH", tmp_path / "missing.ttf")
        font = template_b.get_font(30)
        assert font is not None


class TestTemplateBDrawSidebarBackground:
    def test_returns_rgb_image_of_correct_size(self):
        sidebar = template_b.draw_sidebar_background(
            sidebar_w=576, canvas_h=1080, style_key="blue"
        )
        assert isinstance(sidebar, Image.Image)
        assert sidebar.size == (576, 1080)

    def test_blue_style_uses_deep_navy_background(self):
        sidebar = template_b.draw_sidebar_background(
            sidebar_w=100, canvas_h=100, style_key="blue"
        )
        r, g, b = sidebar.getpixel((50, 50))
        assert r < 10


class TestTemplateARenderThumbnail:
    def test_creates_output_thumbnail_jpeg(self, template_workspace):
        video, ws = template_workspace
        result = template_a.render_thumbnail(video)
        thumbnail = ws / "thumbnail.jpg"
        assert thumbnail.exists()
        assert str(thumbnail) == result
        img = Image.open(str(thumbnail))
        assert img.format == "JPEG"

    def test_raises_if_selected_jpg_missing(self, template_workspace):
        video, ws = template_workspace
        (ws / "selected.jpg").unlink()
        with pytest.raises(MissingThumbnailDataError):
            template_a.render_thumbnail(video)


class TestTemplateBRenderThumbnail:
    def test_creates_output_thumbnail_jpeg(self, template_workspace):
        video, ws = template_workspace
        result = template_b.render_thumbnail(video)
        thumbnail = ws / "thumbnail.jpg"
        assert thumbnail.exists()
        assert str(thumbnail) == result
        img = Image.open(str(thumbnail))
        assert img.format == "JPEG"

    def test_output_has_expected_canvas_size(self, template_workspace):
        video, ws = template_workspace
        template_b.render_thumbnail(video)
        img = Image.open(str(ws / "thumbnail.jpg"))
        assert img.size == (1920, 1080)

    def test_raises_if_selected_jpg_missing(self, template_workspace):
        video, ws = template_workspace
        (ws / "selected.jpg").unlink()
        with pytest.raises(MissingThumbnailDataError):
            template_b.render_thumbnail(video)
