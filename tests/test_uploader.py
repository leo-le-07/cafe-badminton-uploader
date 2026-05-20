import json
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import pytest

import config
from custom_exceptions import VideoAlreadyUploadedError
from schemas import MatchMetadata, UploadedRecord
from uploader import (
    get_videos_ready_for_upload,
    save_upload_record,
    set_thumbnail_for_video,
    update_video_visibility_for_video,
    upload_video_with_idempotency,
)
from utils import get_uploaded_record

_METADATA = MatchMetadata(
    match_type="Men's Singles",
    team1_names=["Leo"],
    team2_names=["Khanh"],
    tournament="Cafe Game",
    title="Leo vs Khanh | Cafe Game",
    description="Description",
    category="17",
)

_UPLOADED_RECORD = UploadedRecord(
    video_id="vid123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=False,
    youtube_link="https://youtu.be/vid123",
)


@pytest.fixture
def video_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path)
    video = tmp_path / "ms_LeovsKhanh.mov"
    video.write_bytes(b"fake video content" * 100)
    workspace = tmp_path / "ms_LeovsKhanh"
    workspace.mkdir()
    (workspace / "metadata.json").write_text(
        json.dumps(asdict(_METADATA)), encoding="utf-8"
    )
    return video, workspace


class TestSaveUploadRecord:
    def test_writes_json_file(self, video_workspace):
        video, workspace = video_workspace
        save_upload_record(video, "vid123", thumbnail_set=False)
        upload_file = workspace / "upload.json"
        assert upload_file.exists()
        data = json.loads(upload_file.read_text())
        assert data["video_id"] == "vid123"
        assert data["thumbnail_set"] is False
        assert data["youtube_link"] == "https://youtu.be/vid123"

    def test_preserves_uploaded_at_on_second_write(self, video_workspace):
        video, workspace = video_workspace
        save_upload_record(video, "vid123", thumbnail_set=False)
        first_at = json.loads((workspace / "upload.json").read_text())["uploaded_at"]
        save_upload_record(video, "vid123", thumbnail_set=True)
        second_at = json.loads((workspace / "upload.json").read_text())["uploaded_at"]
        assert first_at == second_at

    def test_sets_thumbnail_set_true(self, video_workspace):
        video, _ = video_workspace
        save_upload_record(video, "vid123", thumbnail_set=True)
        record = get_uploaded_record(video)
        assert record is not None
        assert record.thumbnail_set is True


class TestGetVideosReadyForUpload:
    def test_excludes_path_with_existing_upload_record(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        save_upload_record(video, "vid123", thumbnail_set=False)
        assert get_videos_ready_for_upload([video]) == []

    def test_excludes_path_with_missing_metadata(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "metadata.json").unlink()
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        assert get_videos_ready_for_upload([video]) == []

    def test_excludes_path_with_missing_thumbnail(self, video_workspace):
        video, _ = video_workspace
        assert get_videos_ready_for_upload([video]) == []

    def test_includes_path_with_metadata_and_thumbnail(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        assert get_videos_ready_for_upload([video]) == [video]


class TestUploadVideoWithIdempotency:
    def test_raises_if_already_uploaded(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        with pytest.raises(VideoAlreadyUploadedError):
            upload_video_with_idempotency(str(video))

    def test_uploads_and_saves_record(self, video_workspace):
        video, workspace = video_workspace
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.insert.return_value.next_chunk.return_value = (
            None,
            {"id": "new_vid456"},
        )
        with patch("uploader.get_client", return_value=mock_youtube):
            result = upload_video_with_idempotency(str(video))
        assert result.video_id == "new_vid456"
        assert (workspace / "upload.json").exists()

    def test_uses_processed_video_when_it_exists(self, video_workspace):
        video, workspace = video_workspace
        processed = workspace / "processed.mov"
        processed.write_bytes(b"processed video" * 100)

        with patch("uploader.get_client"), patch("uploader.upload") as mock_upload:
            mock_upload.return_value = "proc_vid789"
            upload_video_with_idempotency(str(video))
            upload_path_used = mock_upload.call_args[0][1]

        assert upload_path_used == processed


class TestSetThumbnailForVideo:
    def test_raises_if_no_upload_record(self, video_workspace):
        video, _ = video_workspace
        with pytest.raises(RuntimeError, match="not uploaded"):
            set_thumbnail_for_video(str(video))

    def test_skips_if_thumbnail_already_set(self, video_workspace):
        video, workspace = video_workspace
        record = UploadedRecord(
            video_id="vid123",
            uploaded_at="2026-01-01T00:00:00",
            thumbnail_set=True,
            youtube_link="https://youtu.be/vid123",
        )
        (workspace / "upload.json").write_text(
            json.dumps(asdict(record)), encoding="utf-8"
        )
        with patch("uploader.get_client") as mock_client:
            set_thumbnail_for_video(str(video))
            mock_client.assert_not_called()

    def test_sets_thumbnail_and_updates_record(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        mock_youtube = MagicMock()
        mock_youtube.thumbnails.return_value.set.return_value.execute.return_value = {}
        with patch("uploader.get_client", return_value=mock_youtube):
            set_thumbnail_for_video(str(video))
        record = get_uploaded_record(video)
        assert record is not None
        assert record.thumbnail_set is True


class TestUpdateVideoVisibilityForVideo:
    def test_raises_if_no_upload_record(self, video_workspace):
        video, _ = video_workspace
        with pytest.raises(RuntimeError, match="not uploaded"):
            update_video_visibility_for_video(str(video))

    def test_calls_videos_update(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.update.return_value.execute.return_value = {}
        with patch("uploader.get_client", return_value=mock_youtube):
            update_video_visibility_for_video(str(video))
        mock_youtube.videos.return_value.update.assert_called_once()

    def test_raises_on_error_response(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        mock_youtube = MagicMock()
        mock_youtube.videos.return_value.update.return_value.execute.return_value = {
            "error": {"message": "Quota exceeded"}
        }
        with patch("uploader.get_client", return_value=mock_youtube):
            with pytest.raises(RuntimeError, match="Failed to update video visibility"):
                update_video_visibility_for_video(str(video))
