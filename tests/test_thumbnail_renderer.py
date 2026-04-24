from unittest.mock import patch
from thumbnail_enhancement.renderer import render_thumbnail


def test_render_thumbnail_skips_if_thumbnail_jpg_exists(tmp_path):
    thumbnail = tmp_path / "thumbnail.jpg"
    thumbnail.write_bytes(b"existing")

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    with patch("thumbnail_enhancement.renderer.utils.get_thumbnail_path", return_value=thumbnail):
        with patch("thumbnail_enhancement.renderer.get_template_module") as mock_get_template:
            result = render_thumbnail(str(video_path))
            mock_get_template.assert_not_called()

    assert result == str(thumbnail)
    assert thumbnail.read_bytes() == b"existing"


def test_render_thumbnail_proceeds_if_thumbnail_jpg_missing(tmp_path):
    thumbnail = tmp_path / "thumbnail.jpg"

    video_path = tmp_path / "ms_LeovsKhanh.mov"
    video_path.touch()

    mock_template = patch("thumbnail_enhancement.renderer.get_template_module")
    mock_path = patch("thumbnail_enhancement.renderer.utils.get_thumbnail_path", return_value=thumbnail)

    with mock_path, mock_template as mock_get_template:
        mock_get_template.return_value.render_thumbnail.return_value = str(thumbnail)
        render_thumbnail(str(video_path))
        mock_get_template.assert_called_once()
