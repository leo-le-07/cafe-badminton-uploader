import json
from dataclasses import asdict

import pytest

import config
from schemas import MatchMetadata, UploadedRecord
from utils import (
    SUPPORTED_IMAGE_EXTENSIONS,
    get_candidate_dir,
    get_metadata,
    get_metadata_path,
    get_processed_video_path,
    get_selected_candidate_path,
    get_thumbnail_path,
    get_top_ranked_candidates_dir,
    get_upload_record_path,
    get_uploaded_record,
    get_workspace_dir,
    scan_videos,
)

_METADATA = MatchMetadata(
    match_type="Men's Singles",
    team1_names=["Leo"],
    team2_names=["Khanh"],
    tournament="Cafe Game",
    title="Leo vs Khanh | Cafe Game",
    description="Description",
    category="17",
)

_RECORD = UploadedRecord(
    video_id="vid123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=False,
    youtube_link="https://youtu.be/vid123",
)


@pytest.fixture
def patched_input(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    return tmp_path


class TestScanVideos:
    def test_returns_only_mov_files(self, tmp_path):
        (tmp_path / "match1.mov").touch()
        (tmp_path / "match2.MOV").touch()
        (tmp_path / "match3.mp4").touch()
        (tmp_path / "notes.txt").touch()
        results = list(scan_videos(tmp_path))
        suffixes = {p.suffix for p in results}
        assert suffixes == {".mov", ".MOV"}
        assert len(results) == 2

    def test_ignores_directories(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "match.mov").touch()
        results = list(scan_videos(tmp_path))
        assert all(p.is_file() for p in results)

    def test_empty_directory_returns_empty(self, tmp_path):
        assert list(scan_videos(tmp_path)) == []


class TestSupportedImageExtensions:
    def test_contains_common_image_formats(self):
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
            assert ext in SUPPORTED_IMAGE_EXTENSIONS

    def test_does_not_contain_video_extensions(self):
        assert ".mov" not in SUPPORTED_IMAGE_EXTENSIONS
        assert ".mp4" not in SUPPORTED_IMAGE_EXTENSIONS


class TestPathHelpers:
    def test_get_workspace_dir(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert get_workspace_dir(video) == patched_input / "ms_LeovsKhanh"

    def test_get_candidate_dir(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert (
            get_candidate_dir(video) == patched_input / "ms_LeovsKhanh" / "candidates"
        )

    def test_get_top_ranked_candidates_dir(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert (
            get_top_ranked_candidates_dir(video)
            == patched_input / "ms_LeovsKhanh" / "top_candidates"
        )

    def test_get_metadata_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert (
            get_metadata_path(video)
            == patched_input / "ms_LeovsKhanh" / "metadata.json"
        )

    def test_get_selected_candidate_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert (
            get_selected_candidate_path(video)
            == patched_input / "ms_LeovsKhanh" / "selected.jpg"
        )

    def test_get_thumbnail_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert (
            get_thumbnail_path(video)
            == patched_input / "ms_LeovsKhanh" / "thumbnail.jpg"
        )

    def test_get_processed_video_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert (
            get_processed_video_path(video)
            == patched_input / "ms_LeovsKhanh" / "processed.mov"
        )

    def test_get_upload_record_path(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        assert (
            get_upload_record_path(video)
            == patched_input / "ms_LeovsKhanh" / "upload.json"
        )


class TestGetMetadata:
    def test_reads_and_returns_match_metadata(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        ws = patched_input / "ms_LeovsKhanh"
        ws.mkdir()
        (ws / "metadata.json").write_text(
            json.dumps(asdict(_METADATA)), encoding="utf-8"
        )
        result = get_metadata(video)
        assert result.match_type == "Men's Singles"
        assert result.team1_names == ["Leo"]
        assert result.team2_names == ["Khanh"]


class TestGetUploadedRecord:
    def test_returns_none_when_file_missing(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        (patched_input / "ms_LeovsKhanh").mkdir()
        assert get_uploaded_record(video) is None

    def test_returns_upload_record_when_file_present(self, patched_input):
        video = patched_input / "ms_LeovsKhanh.mov"
        ws = patched_input / "ms_LeovsKhanh"
        ws.mkdir()
        (ws / "upload.json").write_text(json.dumps(asdict(_RECORD)), encoding="utf-8")
        result = get_uploaded_record(video)
        assert result is not None
        assert result.video_id == "vid123"
        assert result.thumbnail_set is False
