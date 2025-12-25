import config
from pathlib import Path
import cv2
import shutil

from utils import get_selected_candidate_path, scan_videos, get_top_candidates_dir


def select_thumbnail(video_path: Path):
    video_stem = video_path.stem
    top_candidates_dir = get_top_candidates_dir(video_path)

    images = list(top_candidates_dir.glob("*.jpg"))

    if not images:
        print(f"No top candidates found for {video_path.name}")
        return

    images.sort(key=lambda p: int(p.stem.split("_")[1]))

    current_idx = 0
    total_images = len(images)
    selected_image = None

    window_name = f"Select Thumbnail for {video_stem}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    print(f"\n--- Selecting thumbnail for: {video_stem} ---")
    print(f"Showing top {total_images} ranked candidates")
    print("Controls: [H/L]=Nav  [Enter]=Select  [S]=Default(First)")

    while True:
        img_path = images[current_idx]
        img = cv2.imread(str(img_path))

        if img is None:
            print(f"Error loading image: {img_path}")
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
            print(f"Selected: {img_path.name}")
            break

    cv2.destroyWindow(window_name)
    cv2.waitKey(1)  # Give OpenCV 1ms to process the window destruction

    if selected_image:
        selected_path = get_selected_candidate_path(video_path)
        shutil.copyfile(selected_image, selected_path)


def run():
    videos = scan_videos(config.INPUT_DIR)

    for video_file in videos:
        select_thumbnail(video_file)

    cv2.destroyAllWindows()
    cv2.waitKey(1)


if __name__ == "__main__":
    run()
