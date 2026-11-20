import json
from dataclasses import asdict
from unittest.mock import MagicMock, patch

import httplib2
import pytest
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

import config
from custom_exceptions import (
    AuthRequiredError,
    QuotaExceededError,
    VideoAlreadyUploadedError,
)
from schemas import MatchMetadata, UploadedRecord
from uploader import (
    UPLOAD_SESSION_FILE,
    is_quota_error,
    save_upload_record,
    set_thumbnail_for_video,
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


def _http_error(status: int, reason: str) -> HttpError:
    body = {
        "error": {
            "code": status,
            "message": reason,
            "errors": [{"domain": "youtube", "reason": reason, "message": reason}],
        }
    }
    return HttpError(
        httplib2.Response({"status": status}), json.dumps(body).encode("utf-8")
    )


def _progress(fraction: float) -> MagicMock:
    status = MagicMock()
    status.progress.return_value = fraction
    return status


def _write_session(workspace, resumable_uri: str, file_size: int) -> None:
    (workspace / UPLOAD_SESSION_FILE).write_text(
        json.dumps({"resumable_uri": resumable_uri, "file_size": file_size}),
        encoding="utf-8",
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


def test_is_quota_error():
    assert is_quota_error(_http_error(429, "rateLimitExceeded"))
    assert is_quota_error(_http_error(403, "quotaExceeded"))
    assert is_quota_error(_http_error(403, "uploadLimitExceeded"))
    assert not is_quota_error(_http_error(403, "forbidden"))
    assert not is_quota_error(_http_error(500, "backendError"))


class TestResumableSession:
    def test_session_uri_is_saved_before_upload_finishes(self, video_workspace):
        video, workspace = video_workspace
        request = MagicMock()
        request.resumable_uri = None

        def first_chunk():
            request.resumable_uri = "https://up/1"
            return _progress(0.5), None

        calls = iter([first_chunk, ConnectionError("dropped")])

        def next_chunk():
            step = next(calls)
            if isinstance(step, Exception):
                raise step
            return step()

        request.next_chunk.side_effect = next_chunk
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value = request

        with patch("uploader.get_client", return_value=youtube):
            with pytest.raises(ConnectionError):
                upload_video_with_idempotency(str(video))

        session = json.loads((workspace / UPLOAD_SESSION_FILE).read_text())
        assert session == {
            "resumable_uri": "https://up/1",
            "file_size": video.stat().st_size,
        }
        assert not (workspace / "upload.json").exists()

    def test_restart_resumes_saved_session_instead_of_starting_new(
        self, video_workspace
    ):
        video, workspace = video_workspace
        _write_session(workspace, "https://up/saved", video.stat().st_size)
        request = MagicMock()
        seen = {}

        def next_chunk():
            seen["uri"] = request.resumable_uri
            seen["in_error_state"] = request._in_error_state
            return None, {"id": "resumed_vid"}

        request.next_chunk.side_effect = next_chunk
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value = request

        with patch("uploader.get_client", return_value=youtube):
            result = upload_video_with_idempotency(str(video))

        assert seen == {"uri": "https://up/saved", "in_error_state": True}
        assert youtube.videos.return_value.insert.call_count == 1
        assert result.video_id == "resumed_vid"
        assert json.loads((workspace / "upload.json").read_text())["video_id"] == (
            "resumed_vid"
        )
        assert not (workspace / UPLOAD_SESSION_FILE).exists()

    def test_expired_session_falls_back_to_fresh_upload(self, video_workspace):
        video, workspace = video_workspace
        _write_session(workspace, "https://up/expired", video.stat().st_size)
        old_request = MagicMock()
        old_request.next_chunk.side_effect = _http_error(404, "notFound")
        new_request = MagicMock()
        seen = {}

        def fresh_chunk():
            seen["session_exists"] = (workspace / UPLOAD_SESSION_FILE).exists()
            seen["uri"] = new_request.resumable_uri
            return None, {"id": "fresh_vid"}

        new_request.next_chunk.side_effect = fresh_chunk
        youtube = MagicMock()
        youtube.videos.return_value.insert.side_effect = [old_request, new_request]

        with patch("uploader.get_client", return_value=youtube):
            result = upload_video_with_idempotency(str(video))

        assert youtube.videos.return_value.insert.call_count == 2
        assert seen["session_exists"] is False
        assert seen["uri"] != "https://up/expired"
        assert result.video_id == "fresh_vid"
        assert not (workspace / UPLOAD_SESSION_FILE).exists()

    def test_session_for_different_file_size_is_ignored(self, video_workspace):
        video, workspace = video_workspace
        _write_session(workspace, "https://up/other", video.stat().st_size + 1)
        request = MagicMock()
        seen = {}

        def next_chunk():
            seen["uri"] = request.resumable_uri
            seen["in_error_state"] = request._in_error_state
            return None, {"id": "fresh_vid"}

        request.next_chunk.side_effect = next_chunk
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value = request

        with patch("uploader.get_client", return_value=youtube):
            result = upload_video_with_idempotency(str(video))

        assert seen["uri"] != "https://up/other"
        assert seen["in_error_state"] is not True
        assert result.video_id == "fresh_vid"

    def test_session_is_matched_against_processed_video_size(self, video_workspace):
        video, workspace = video_workspace
        processed = workspace / "processed.mov"
        processed.write_bytes(b"processed video" * 300)
        _write_session(workspace, "https://up/processed", processed.stat().st_size)
        request = MagicMock()
        seen = {}

        def next_chunk():
            seen["uri"] = request.resumable_uri
            return None, {"id": "proc_vid"}

        request.next_chunk.side_effect = next_chunk
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value = request

        with patch("uploader.get_client", return_value=youtube):
            upload_video_with_idempotency(str(video))

        assert seen["uri"] == "https://up/processed"


class TestErrorClassification:
    def test_quota_http_error_becomes_quota_exceeded(self, video_workspace):
        video, workspace = video_workspace
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value.next_chunk.side_effect = (
            _http_error(403, "uploadLimitExceeded")
        )
        with patch("uploader.get_client", return_value=youtube):
            with pytest.raises(QuotaExceededError):
                upload_video_with_idempotency(str(video))
        assert not (workspace / "upload.json").exists()

    def test_other_http_error_propagates_unchanged(self, video_workspace):
        video, _ = video_workspace
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value.next_chunk.side_effect = (
            _http_error(500, "backendError")
        )
        with patch("uploader.get_client", return_value=youtube):
            with pytest.raises(HttpError):
                upload_video_with_idempotency(str(video))

    def test_missing_token_becomes_auth_required(self, video_workspace):
        video, _ = video_workspace
        with patch(
            "uploader.get_client",
            side_effect=RuntimeError("OAuth token not found. Run auth setup."),
        ):
            with pytest.raises(AuthRequiredError):
                upload_video_with_idempotency(str(video))

    def test_revoked_token_becomes_auth_required(self, video_workspace):
        video, _ = video_workspace
        youtube = MagicMock()
        youtube.videos.return_value.insert.return_value.next_chunk.side_effect = (
            RefreshError("invalid_grant: Token has been expired or revoked.")
        )
        with patch("uploader.get_client", return_value=youtube):
            with pytest.raises(AuthRequiredError):
                upload_video_with_idempotency(str(video))

    def test_set_thumbnail_maps_auth_errors(self, video_workspace):
        video, workspace = video_workspace
        (workspace / "upload.json").write_text(
            json.dumps(asdict(_UPLOADED_RECORD)), encoding="utf-8"
        )
        (workspace / "thumbnail.jpg").write_bytes(b"img")
        with patch("uploader.get_client", side_effect=RuntimeError("OAuth token")):
            with pytest.raises(AuthRequiredError):
                set_thumbnail_for_video(str(video))

        youtube = MagicMock()
        youtube.thumbnails.return_value.set.return_value.execute.side_effect = (
            RefreshError("revoked")
        )
        with patch("uploader.get_client", return_value=youtube):
            with pytest.raises(AuthRequiredError):
                set_thumbnail_for_video(str(video))
