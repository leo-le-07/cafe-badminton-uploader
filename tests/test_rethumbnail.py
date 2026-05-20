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
