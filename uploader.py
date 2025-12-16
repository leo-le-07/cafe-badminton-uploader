from googleapiclient.http import MediaFileUpload
from auth_service import get_client
import config
from stage_1 import CATEGORY_SPORTS, scan_videos
from pathlib import Path
from tqdm import tqdm
from typing import Any

from utils import get_metadata, get_thumbnail_path

CHUNK_SIZE_MB = 1024 * 1024 * 16  # 16MB


def filter_ready_upload(video_paths: list[Path]) -> list[Path]:
    result = []

    for video_file in video_paths:
        workspace_dir = config.INPUT_DIR / video_file.stem
        if not workspace_dir.is_dir():
            continue

        metadata_path = workspace_dir / "metadata.json"
        thumbnail_path = workspace_dir / "thumbnail.jpg"

        if not metadata_path.exists() or not thumbnail_path.exists():
            continue

        result.append(video_file)

    return result


def upload(youtube_client: Any, video_path: Path, metadata: dict) -> str | None:
    result = None
    category = metadata.get("category", CATEGORY_SPORTS)
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


def run():
    video_paths = list(scan_videos(config.INPUT_DIR))
    video_paths = filter_ready_upload(video_paths)
    client = get_client()

    for video_path in video_paths:
        thumbnail_path = get_thumbnail_path(video_path)
        metadata = get_metadata(video_path)

        video_id = upload(client, video_path, metadata)

        if not video_id:
            print(f"Upload video failed {video_path}")
            continue

        set_thumbnail(client, video_id, thumbnail_path)


if __name__ == "__main__":
    run()
