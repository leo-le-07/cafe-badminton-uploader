from googleapiclient.http import MediaFileUpload
from auth_service import get_client
import config
import constants
from pathlib import Path
from tqdm import tqdm
from typing import Any
from datetime import datetime
import json
from utils import (
    get_metadata,
    get_thumbnail_path,
    get_upload_record_path,
    scan_videos,
    get_metadata_path,
)

CHUNK_SIZE_MB = 1024 * 1024 * 16  # 16MB


def get_videos_ready_for_upload(video_paths: list[Path]) -> list[Path]:
    result = []

    for video_path in video_paths:
        if get_upload_record_path(video_path).exists():
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


def upload(youtube_client: Any, video_path: Path, metadata: dict) -> str | None:
    result = None
    category = metadata.get("category", constants.CATEGORY_SPORTS)
    description = metadata.get("description", "")
    title = metadata.get("title", video_path.stem)
    privacy_status = metadata.get("privacyStatus", "private")

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

    total_size = video_path.stat().st_size  # bytes
    pbar = tqdm(total=total_size, unit="B", unit_scale=True, desc="Upload progress")

    response = None
    previous_progress = 0

    while response is None:
        status, response = request.next_chunk()
        if status:
            # convert percentage to actual uploaded bytes
            current_progress = int(status.progress() * total_size)

            pbar.update(current_progress - previous_progress)
            previous_progress = current_progress

    pbar.close()

    result = response.get("id")

    return result


def set_thumbnail(youtube_client: Any, video_id: str, thumbnail_path: Path) -> bool:
    request = youtube_client.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
    )

    response = request.execute()
    return "error" not in response


def save_upload_record(video_path: Path, video_id: str, thumbnail_set: bool):
    upload_record_path = get_upload_record_path(video_path)
    upload_record = {
        "videoId": video_id,
        "uploadedAt": datetime.now().isoformat(),
        "thumbnailSet": thumbnail_set,
        "youtubeLink": f"https://youtu.be/{video_id}",
    }

    with open(upload_record_path, "w", encoding="utf-8") as f:
        json.dump(upload_record, f, ensure_ascii=False, indent=4)


def run():
    video_paths = list(scan_videos(config.INPUT_DIR))
    video_paths = get_videos_ready_for_upload(video_paths)
    client = get_client()

    for video_path in video_paths:
        thumbnail_path = get_thumbnail_path(video_path)
        metadata = get_metadata(video_path)

        video_id = upload(client, video_path, metadata)

        if not video_id:
            print(f"Upload video failed {video_path}")
            continue

        thumbnail_set = set_thumbnail(client, video_id, thumbnail_path)
        save_upload_record(video_path, video_id, thumbnail_set)


if __name__ == "__main__":
    run()
