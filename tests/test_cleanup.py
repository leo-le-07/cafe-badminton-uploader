import json
from dataclasses import asdict

import pytest

import config
from cleanup import cleanup_video
from custom_exceptions import NoUploadedRecordError
from schemas import UploadedRecord

_RECORD = UploadedRecord(
    video_id="vid123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=True,
    youtube_link="https://youtu.be/vid123",
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    (tmp_path / "completed").mkdir()

    video = tmp_path / "ms_LeovsKhanh.mov"
    video.write_bytes(b"video content")

    ws = tmp_path / "ms_LeovsKhanh"
    ws.mkdir()
    (ws / "upload.json").write_text(json.dumps(asdict(_RECORD)), encoding="utf-8")
    (ws / "thumbnail.jpg").write_bytes(b"img")

    return video, ws


class TestCleanupVideo:
    def test_raises_if_no_upload_record(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
        video = tmp_path / "ms_LeovsKhanh.mov"
        video.touch()
        (tmp_path / "ms_LeovsKhanh").mkdir()
        with pytest.raises(NoUploadedRecordError):
            cleanup_video(str(video))

    def test_raises_if_upload_record_has_no_video_id(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
        video = tmp_path / "ms_LeovsKhanh.mov"
        video.touch()
        ws = tmp_path / "ms_LeovsKhanh"
        ws.mkdir()
        empty_record = UploadedRecord(
            video_id="",
            uploaded_at="2026-01-01T00:00:00",
            thumbnail_set=False,
            youtube_link="",
        )
        (ws / "upload.json").write_text(
            json.dumps(asdict(empty_record)), encoding="utf-8"
        )
        with pytest.raises(NoUploadedRecordError):
            cleanup_video(str(video))

    def test_raises_if_workspace_missing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
        video = tmp_path / "ms_LeovsKhanh.mov"
        video.touch()
        with pytest.raises(NoUploadedRecordError):
            cleanup_video(str(video))

    def test_moves_video_and_workspace_to_completed(self, workspace):
        video, ws = workspace
        result = cleanup_video(str(video))
        completed = config.COMPLETED_DIR
        assert not video.exists()
        assert not ws.exists()
        assert (completed / video.name).exists()
        assert (completed / ws.name).exists()
        assert result == str(completed / video.name)
