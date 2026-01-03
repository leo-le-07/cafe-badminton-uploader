from schemas import MatchMetadata, UploadedRecord
from dataclasses import asdict
from googleapiclient.http import MediaFileUpload
from auth_service import get_client
import config
from pathlib import Path
from tqdm import tqdm
from typing import Any, Callable
from datetime import datetime
import json
from utils import (
    get_metadata,
    get_thumbnail_path,
    get_upload_record_path,
    get_uploaded_record,
    scan_videos,
    get_metadata_path,
)

CHUNK_SIZE_MB = 1024 * 1024 * 16  # 16MB


def get_videos_ready_for_upload(video_paths: list[Path]) -> list[Path]:
    result = []

    for video_path in video_paths:
        upload_record = get_uploaded_record(video_path)
        if upload_record:
            continue

        metadata_path = get_metadata_path(video_path)
        thumbnail_path = get_thumbnail_path(video_path)
        if not metadata_path.exists() or not thumbnail_path.exists():
            continue

        try:
            metadata = get_metadata(video_path)
            if not metadata:
                continue
        except (FileNotFoundError, json.JSONDecodeError):
            continue

        result.append(video_path)

    return result


def upload(
    youtube_client: Any,
    video_path: Path,
    metadata: MatchMetadata,
    progress_callback: Callable[[float], None] | None = None,
) -> str:
    category = metadata.category
    description = metadata.description
    title = metadata.title
    privacy_status = metadata.privacy_status

    media = MediaFileUpload(
        video_path, mimetype="video/*", resumable=True, chunksize=CHUNK_SIZE_MB
    )

    request = youtube_client.videos().insert(
        part="snippet,status,contentDetails",
        body={
            "snippet": {
                "categoryId": str(category),
                "description": description,
                "title": title,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=media,
    )

    total_size = video_path.stat().st_size
    response = None
    previous_progress = 0

    while response is None:
        status, response = request.next_chunk()
        if status and progress_callback:
            current_progress = int(status.progress() * total_size)
            progress_percent = (current_progress / total_size) * 100
            progress_callback(progress_percent)
            previous_progress = current_progress

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
    video_path: Path,
    heartbeat_callback: Callable[[float], None] | None = None,
) -> UploadedRecord:
    uploaded_record = get_uploaded_record(video_path)
    if uploaded_record and uploaded_record.video_id:
        return uploaded_record

    metadata = get_metadata(video_path)
    if not metadata:
        raise ValueError("Metadata not found for video upload.")

    youtube_client = get_client()
    video_id = upload(youtube_client, video_path, metadata, heartbeat_callback)
    save_upload_record(video_path, video_id, thumbnail_set=False)

    uploaded_record = get_uploaded_record(video_path)
    if not uploaded_record:
        raise RuntimeError("Failed to retrieve upload record after saving")
    return uploaded_record


def set_thumbnail_for_video(video_path: Path) -> None:
    upload_record = get_uploaded_record(video_path)
    if not upload_record or not upload_record.video_id:
        raise RuntimeError(f"Video not uploaded yet. Cannot set thumbnail for {video_path.name}")
    
    if upload_record.thumbnail_set:
        return
    
    youtube_client = get_client()
    thumbnail_path = get_thumbnail_path(video_path)
    
    if not thumbnail_path.exists():
        raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")
    
    set_thumbnail(youtube_client, upload_record.video_id, thumbnail_path)
    save_upload_record(video_path, upload_record.video_id, thumbnail_set=True)


def save_upload_record(video_path: Path, video_id: str, thumbnail_set: bool) -> None:
    upload_record_path = get_upload_record_path(video_path)
    
    existing_record = get_uploaded_record(video_path)
    uploaded_at = existing_record.uploaded_at if existing_record else datetime.now().isoformat()
    
    upload_record = UploadedRecord(
        video_id=video_id,
        uploaded_at=uploaded_at,
        thumbnail_set=thumbnail_set,
        youtube_link=f"https://youtu.be/{video_id}",
    )

    with open(upload_record_path, "w", encoding="utf-8") as f:
        json.dump(asdict(upload_record), f, ensure_ascii=False, indent=4)


def run():

    video_paths = list(scan_videos(config.INPUT_DIR))
    video_paths = get_videos_ready_for_upload(video_paths)
    client = get_client()

    for video_path in video_paths:
        thumbnail_path = get_thumbnail_path(video_path)
        metadata = get_metadata(video_path)

        total_size = video_path.stat().st_size
        pbar = tqdm(total=total_size, unit="B", unit_scale=True, desc=f"Upload {video_path.name}")

        def progress_callback(percent: float) -> None:
            current_bytes = int((percent / 100) * total_size)
            pbar.n = current_bytes
            pbar.refresh()

        video_id = upload(client, video_path, metadata, progress_callback)
        pbar.close()

        set_thumbnail(client, video_id, thumbnail_path)
        save_upload_record(video_path, video_id, thumbnail_set=True)


if __name__ == "__main__":
    run()
