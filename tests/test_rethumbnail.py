import time

import pytest

from rethumbnail import find_manual_thumbnail


class TestFindManualThumbnail:
    def test_raises_when_no_images(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No manual thumbnail"):
            find_manual_thumbnail(tmp_path)

    def test_returns_single_valid_image(self, tmp_path):
        img = tmp_path / "my_photo.jpg"
        img.write_bytes(b"fake")
        assert find_manual_thumbnail(tmp_path) == img

    def test_picks_most_recently_modified(self, tmp_path):
        older = tmp_path / "old.jpg"
        older.write_bytes(b"old")
        time.sleep(0.05)
        newer = tmp_path / "new.jpg"
        newer.write_bytes(b"new")
        assert find_manual_thumbnail(tmp_path) == newer

    def test_raises_when_only_reserved_names(self, tmp_path):
        (tmp_path / "selected.jpg").write_bytes(b"s")
        (tmp_path / "thumbnail.jpg").write_bytes(b"t")
        with pytest.raises(FileNotFoundError, match="No manual thumbnail"):
            find_manual_thumbnail(tmp_path)

    def test_ignores_reserved_names_returns_valid(self, tmp_path):
        (tmp_path / "selected.jpg").write_bytes(b"s")
        (tmp_path / "thumbnail.jpg").write_bytes(b"t")
        valid = tmp_path / "manual.png"
        valid.write_bytes(b"v")
        assert find_manual_thumbnail(tmp_path) == valid

    def test_accepts_all_supported_extensions(self, tmp_path):
        for ext in [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".bmp",
            ".tiff",
            ".tif",
            ".gif",
            ".heic",
            ".heif",
        ]:
            f = tmp_path / f"image{ext}"
            f.write_bytes(b"data")
        # All are valid; just verify it doesn't raise
        result = find_manual_thumbnail(tmp_path)
        assert result.exists()

    def test_ignores_non_image_files(self, tmp_path):
        (tmp_path / "notes.txt").write_bytes(b"text")
        (tmp_path / "data.json").write_bytes(b"{}")
        with pytest.raises(FileNotFoundError):
            find_manual_thumbnail(tmp_path)


from unittest.mock import MagicMock, patch

from schemas import UploadedRecord
from utils import RENDERED_THUMBNAIL_NAME, SELECTED_CANDIDATE_NAME

from rethumbnail import rethumbnail_video

_RECORD = UploadedRecord(
    video_id="abc123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=True,
    youtube_link="https://youtu.be/abc123",
)


class TestRethumbnailVideo:
    def _setup_workspace(self, tmp_path):
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()
        manual_img = workspace_dir / "manual.jpg"
        manual_img.write_bytes(b"manual-image-bytes")
        old_thumbnail = workspace_dir / RENDERED_THUMBNAIL_NAME
        old_thumbnail.write_bytes(b"old-thumbnail")
        return workspace_dir, manual_img

    def test_replaces_selected_jpg_with_manual_image(self, tmp_path):
        workspace_dir, manual_img = self._setup_workspace(tmp_path)

        with (
            patch("rethumbnail.get_uploaded_record", return_value=_RECORD),
            patch(
                "rethumbnail.render_thumbnail",
                return_value=str(workspace_dir / RENDERED_THUMBNAIL_NAME),
            ),
            patch("rethumbnail.get_client", return_value=MagicMock()),
            patch("rethumbnail.set_thumbnail"),
            patch("rethumbnail.save_upload_record"),
        ):
            rethumbnail_video(workspace_dir)

        selected = workspace_dir / SELECTED_CANDIDATE_NAME
        assert selected.read_bytes() == b"manual-image-bytes"

    def test_deletes_old_thumbnail_before_render(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)
        render_call_order = []

        def fake_render(video_path, *args, **kwargs):
            thumbnail_path = workspace_dir / RENDERED_THUMBNAIL_NAME
            render_call_order.append(thumbnail_path.exists())
            return str(thumbnail_path)

        with (
            patch("rethumbnail.get_uploaded_record", return_value=_RECORD),
            patch("rethumbnail.render_thumbnail", side_effect=fake_render),
            patch("rethumbnail.get_client", return_value=MagicMock()),
            patch("rethumbnail.set_thumbnail"),
            patch("rethumbnail.save_upload_record"),
        ):
            rethumbnail_video(workspace_dir)

        assert render_call_order == [False], (
            "thumbnail.jpg must be deleted before render is called"
        )

    def test_calls_set_thumbnail_with_correct_video_id(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)
        mock_youtube = MagicMock()

        with (
            patch("rethumbnail.get_uploaded_record", return_value=_RECORD),
            patch(
                "rethumbnail.render_thumbnail",
                return_value=str(workspace_dir / RENDERED_THUMBNAIL_NAME),
            ),
            patch("rethumbnail.get_client", return_value=mock_youtube),
            patch("rethumbnail.set_thumbnail") as mock_set,
            patch("rethumbnail.save_upload_record"),
        ):
            rethumbnail_video(workspace_dir)

        mock_set.assert_called_once_with(
            mock_youtube,
            "abc123",
            workspace_dir / RENDERED_THUMBNAIL_NAME,
        )

    def test_saves_upload_record_with_thumbnail_set_true(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)

        with (
            patch("rethumbnail.get_uploaded_record", return_value=_RECORD),
            patch(
                "rethumbnail.render_thumbnail",
                return_value=str(workspace_dir / RENDERED_THUMBNAIL_NAME),
            ),
            patch("rethumbnail.get_client", return_value=MagicMock()),
            patch("rethumbnail.set_thumbnail"),
            patch("rethumbnail.save_upload_record") as mock_save,
        ):
            rethumbnail_video(workspace_dir)

        _, kwargs = mock_save.call_args
        assert kwargs["thumbnail_set"] is True

    def test_raises_when_no_upload_record(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)

        with patch("rethumbnail.get_uploaded_record", return_value=None):
            with pytest.raises(RuntimeError, match="No upload record"):
                rethumbnail_video(workspace_dir)

    def test_raises_when_upload_record_missing_video_id(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)
        record_no_id = UploadedRecord(
            video_id="",
            uploaded_at="2026-01-01T00:00:00",
            thumbnail_set=False,
            youtube_link="",
        )

        with patch("rethumbnail.get_uploaded_record", return_value=record_no_id):
            with pytest.raises(RuntimeError, match="No upload record"):
                rethumbnail_video(workspace_dir)
