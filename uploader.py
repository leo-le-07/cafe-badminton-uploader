from schemas import MatchMetadata, UploadedRecord
from custom_exceptions import (
    AuthRequiredError,
    QuotaExceededError,
    VideoAlreadyUploadedError,
)
from dataclasses import asdict
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import httplib2
import ssl
import time
from auth_service import get_client
import config
from pathlib import Path
from typing import Any, Callable
from datetime import datetime
import json
from utils import (
    write_json_atomic,
    get_metadata,
    get_thumbnail_path,
    get_upload_record_path,
    get_uploaded_record,
    get_processed_video_path,
    get_workspace_dir,
)

CHUNK_SIZE_MB = 1024 * 1024 * 16  # 16MB
UPLOAD_SESSION_FILE = "upload_session.json"

QUOTA_ERROR_REASONS = {"quotaExceeded", "rateLimitExceeded", "uploadLimitExceeded"}
EXPIRED_SESSION_STATUSES = {404, 410}

# googleapiclient retries 5xx/429 responses itself (num_retries), but a
# connection that drops while a chunk is in flight is raised at once. The
# request is then in its error state, so the next next_chunk() asks YouTube
# which bytes arrived and continues from there on the same session.
CHUNK_RETRIES = 5
TRANSPORT_ERRORS = (ConnectionError, TimeoutError, ssl.SSLError, httplib2.HttpLib2Error)
_sleep = time.sleep


def is_quota_error(err: HttpError) -> bool:
    if err.status_code == 429:
        return True
    try:
        errors = json.loads(err.content.decode("utf-8"))["error"]["errors"]
        reasons = {e.get("reason") for e in errors}
    except (ValueError, KeyError, TypeError, AttributeError):
        return False
    return bool(reasons & QUOTA_ERROR_REASONS)


def get_upload_session_path(video_path: Path) -> Path:
    return get_workspace_dir(video_path) / UPLOAD_SESSION_FILE


def load_upload_session(session_path: Path, file_size: int) -> str | None:
    """Return the saved resumable URI if it belongs to a file of this size."""
    try:
        session = json.loads(session_path.read_text(encoding="utf-8"))
        resumable_uri = session["resumable_uri"]
        saved_size = session["file_size"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if saved_size != file_size or not isinstance(resumable_uri, str):
        return None
    return resumable_uri


def save_upload_session(session_path: Path, resumable_uri: str, file_size: int) -> None:
    write_json_atomic(
        session_path, {"resumable_uri": resumable_uri, "file_size": file_size}
    )


def _youtube_client() -> Any:
    try:
        return get_client()
    except RuntimeError as e:
        raise AuthRequiredError(str(e)) from e


def _insert_request(youtube_client: Any, video_path: Path, metadata: MatchMetadata):
    media = MediaFileUpload(
        video_path, mimetype="video/*", resumable=True, chunksize=CHUNK_SIZE_MB
    )

    return youtube_client.videos().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "categoryId": str(metadata.category),
                "description": metadata.description,
                "title": metadata.title,
            },
            "status": {
                "privacyStatus": config.VIDEO_PRIVACY_STATUS,
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=media,
    )


def _send_chunks(
    request: Any,
    total_size: int,
    session_path: Path | None,
    progress_callback: Callable[[float], None] | None,
) -> dict:
    saved_uri = request.resumable_uri
    response = None
    failures = 0

    while response is None:
        try:
            status, response = request.next_chunk(num_retries=CHUNK_RETRIES)
        except TRANSPORT_ERRORS:
            failures += 1
            if failures > CHUNK_RETRIES:
                raise
            _sleep(min(2**failures, 16))
            continue
        failures = 0
        if (
            response is None
            and session_path is not None
            and request.resumable_uri != saved_uri
        ):
            # Persist as soon as the session exists so a restart can resume it
            # instead of creating a second video.
            saved_uri = request.resumable_uri
            save_upload_session(session_path, saved_uri, total_size)
        if status and progress_callback:
            current_progress = int(status.progress() * total_size)
            progress_percent = (current_progress / total_size) * 100
            progress_callback(progress_percent)

    return response


def upload(
    youtube_client: Any,
    video_path: Path,
    metadata: MatchMetadata,
    progress_callback: Callable[[float], None] | None = None,
    session_path: Path | None = None,
) -> str:
    total_size = video_path.stat().st_size
    saved_uri = load_upload_session(session_path, total_size) if session_path else None

    response = None
    if saved_uri:
        request = _insert_request(youtube_client, video_path, metadata)
        # googleapiclient asks the server for the received byte range (empty PUT)
        # before sending the next chunk when the request is in error state.
        request.resumable_uri = saved_uri
        request._in_error_state = True
        try:
            response = _send_chunks(
                request, total_size, session_path, progress_callback
            )
        except HttpError as e:
            if e.status_code not in EXPIRED_SESSION_STATUSES:
                raise
            session_path.unlink(missing_ok=True)

    if response is None:
        request = _insert_request(youtube_client, video_path, metadata)
        response = _send_chunks(request, total_size, session_path, progress_callback)

    video_id = response.get("id")
    if not video_id:
        raise ValueError("Upload response missing video ID")

    return video_id


def set_thumbnail(youtube_client: Any, video_id: str, thumbnail_path: Path) -> None:
    request = youtube_client.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
    )

    response = request.execute()
    if "error" in response:
        raise RuntimeError(f"Failed to set thumbnail: {response.get('error', {})}")


def upload_video_with_idempotency(
    video_path: str,
    heartbeat_callback: Callable[[float], None] | None = None,
) -> UploadedRecord:
    path = Path(video_path)
    uploaded_record = get_uploaded_record(path)
    if uploaded_record and uploaded_record.video_id:
        raise VideoAlreadyUploadedError(
            f"Video {path.name} is already uploaded with video ID {uploaded_record.video_id}. "
            f"YouTube link: {uploaded_record.youtube_link}"
        )

    metadata = get_metadata(path)
    if not metadata:
        raise ValueError("Metadata not found for video upload.")

    processed_path = get_processed_video_path(path)
    upload_path = processed_path if processed_path.exists() else path

    session_path = get_upload_session_path(path)
    youtube_client = _youtube_client()
    try:
        video_id = upload(
            youtube_client,
            upload_path,
            metadata,
            heartbeat_callback,
            session_path=session_path,
        )
    except RefreshError as e:
        raise AuthRequiredError(str(e)) from e
    except HttpError as e:
        if is_quota_error(e):
            raise QuotaExceededError(str(e)) from e
        raise
    save_upload_record(path, video_id, thumbnail_set=False)
    session_path.unlink(missing_ok=True)

    uploaded_record = get_uploaded_record(path)
    if not uploaded_record:
        raise RuntimeError("Failed to retrieve upload record after saving")
    return uploaded_record


def set_thumbnail_for_video(video_path: str) -> None:
    path = Path(video_path)
    upload_record = get_uploaded_record(path)
    if not upload_record or not upload_record.video_id:
        raise RuntimeError(
            f"Video not uploaded yet. Cannot set thumbnail for {path.name}"
        )

    if upload_record.thumbnail_set:
        return

    youtube_client = _youtube_client()
    thumbnail_path = get_thumbnail_path(path)

    if not thumbnail_path.exists():
        raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")

    try:
        set_thumbnail(youtube_client, upload_record.video_id, thumbnail_path)
    except RefreshError as e:
        raise AuthRequiredError(str(e)) from e
    except HttpError as e:
        if is_quota_error(e):
            raise QuotaExceededError(str(e)) from e
        raise
    save_upload_record(path, upload_record.video_id, thumbnail_set=True)


def save_upload_record(video_path: Path, video_id: str, thumbnail_set: bool) -> None:
    upload_record_path = get_upload_record_path(video_path)

    existing_record = get_uploaded_record(video_path)
    uploaded_at = (
        existing_record.uploaded_at if existing_record else datetime.now().isoformat()
    )

    upload_record = UploadedRecord(
        video_id=video_id,
        uploaded_at=uploaded_at,
        thumbnail_set=thumbnail_set,
        youtube_link=f"https://youtu.be/{video_id}",
    )

    write_json_atomic(upload_record_path, asdict(upload_record), indent=4)
