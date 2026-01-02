import config
from pathlib import Path
import cv2
import shutil
import asyncio
from typing import Optional

from utils import (
    get_selected_candidate_path,
    scan_videos,
    get_top_ranked_candidates_dir,
)
from logger import get_logger

logger = get_logger(__name__)


def _select_thumbnail_gui(video_path: Path) -> Optional[Path]:
    video_stem = video_path.stem
    top_candidates_dir = get_top_ranked_candidates_dir(video_path)

    images = list(top_candidates_dir.glob("*.jpg"))

    if not images:
        logger.warning(f"No top candidates found for {video_path.name}")
        return None

    images.sort(key=lambda p: int(p.stem.split("_")[1]))

    current_idx = 0
    total_images = len(images)
    selected_image = None

    window_name = f"Select Thumbnail for {video_stem}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    logger.info(f"Selecting thumbnail for: {video_stem} ({total_images} candidates)")

    while True:
        img_path = images[current_idx]
        img = cv2.imread(str(img_path))

        if img is None:
            logger.error(f"Error loading image: {img_path}")
            break

        display_img = img.copy()
        cv2.putText(
            display_img,
            f"Video: {video_stem}",
            (30, 60),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.2,
            (0, 255, 255),
            3,
        )

        text = f"Candidate {current_idx + 1}/{total_images} | Frame: {img_path.name}"
        cv2.putText(
            display_img, text, (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3
        )

        cv2.imshow(window_name, display_img)

        key = cv2.waitKey(0) & 0xFF

        if key in [ord("l"), 83]:  # 'l' or Right Arrow
            current_idx = (current_idx + 1) % total_images

        elif key in [ord("h"), 81]:  # 'h' or Left Arrow
            current_idx = (current_idx - 1 + total_images) % total_images

        elif key in [ord("s"), 13]:  # Enter or 's' -> SELECT
            selected_image = img_path
            logger.info(f"Selected: {img_path.name}")
            break

    cv2.destroyWindow(window_name)
    cv2.waitKey(1)  # Give OpenCV 1ms to process the window destruction

    return selected_image


def select_thumbnail(video_path: Path):
    selected_image = _select_thumbnail_gui(video_path)
    
    if selected_image:
        selected_path = get_selected_candidate_path(video_path)
        shutil.copyfile(selected_image, selected_path)


async def select_thumbnail_with_workflow(workflow_handle) -> None:
    video_path_str = await workflow_handle.query("get_video_path")
    video_path = Path(video_path_str)
    
    selected_image = _select_thumbnail_gui(video_path)
    
    if selected_image:
        selected_path = get_selected_candidate_path(video_path)
        shutil.copyfile(selected_image, selected_path)
        
        try:
            await workflow_handle.signal("thumbnail_selected")
            logger.info(f"Selected thumbnail saved and signal sent for {video_path.name}")
        except Exception as e:
            logger.error(f"Error sending signal to workflow: {e}")
            raise
    else:
        logger.warning("No thumbnail selected. Workflow will remain waiting.")


def run():
    videos = scan_videos(config.INPUT_DIR)

    for video_file in videos:
        select_thumbnail(video_file)

    cv2.destroyAllWindows()
    cv2.waitKey(1)


if __name__ == "__main__":
    run()
