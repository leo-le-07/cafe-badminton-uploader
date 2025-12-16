from googleapiclient.http import MediaFileUpload
import json
from auth_service import authenticate_youtube
import config
from stage_1 import CATEGORY_SPORTS, get_workspace_dir, scan_videos
from pathlib import Path
from tqdm import tqdm
from typing import Any

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


if __name__ == "__main__":
    video_paths = list(scan_videos(config.INPUT_DIR))
    video_paths = filter_ready_upload(video_paths)
    youtube_client = authenticate_youtube()

    for video_path in video_paths:
        workspace_dir = get_workspace_dir(video_path)
        metadata_path = workspace_dir / "metadata.json"
        thumbnail_path = workspace_dir / "thumbnail.jpg"
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        video_id = upload(youtube_client, video_path, metadata)

        if not video_id:
            print(f"Upload video failed {video_path}")
            continue

        set_thumbnail(youtube_client, video_id, thumbnail_path)
