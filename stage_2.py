import config
from pathlib import Path
import cv2
import shutil

from stage_1 import scan_videos


def select_thumbnail(video_file: Path):
    video_name = video_file.stem
    video_folder = config.INPUT_DIR / video_name
    candidate_dir = video_folder / "candidates"
    images = list(candidate_dir.glob("frame_*.jpg"))

    if not images:
        print(f"No candidate thumbnails found for {video_file.name}")
        return

    images.sort(key=lambda p: int(p.stem.split("_")[1]))

    current_idx = 0
    total_images = len(images)
    selected_image = None

    window_name = f"Select Thumbnail for {video_name}"
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(window_name, 1280, 720)

    print(f"\n--- Selecting thumbnail for: {video_name} ---")
    print("Controls: [A/D]=Nav  [Enter]=Select  [S]=Default(Middle)")

    while True:
        img_path = images[current_idx]
        img = cv2.imread(str(img_path))

        if img is None:
            print(f"Error loading image: {img_path}")
            break

        display_img = img.copy()
        cv2.putText(
            display_img,
            f"Video: {video_name}",
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

        if key in [ord("d"), 83]:  # 'd' or Right Arrow
            current_idx = (current_idx + 1) % total_images

        elif key in [ord("a"), 81]:  # 'a' or Left Arrow
            current_idx = (current_idx - 1 + total_images) % total_images

        elif key in [ord("s"), 13]:  # Enter or 's' -> SELECT
            selected_image = img_path
            print(f"Selected: {img_path.name}")
            break

    cv2.destroyWindow(window_name)

    if selected_image:
        selected_path = video_folder / "selected.jpg"
        shutil.copyfile(selected_image, selected_path)
        print(f"Selected frame saved to: {selected_path}")


if __name__ == "__main__":
    videos = scan_videos(config.INPUT_DIR)

    for video_file in videos:
        select_thumbnail(video_file)
