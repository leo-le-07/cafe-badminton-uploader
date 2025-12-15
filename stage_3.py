from pathlib import Path

import numpy as np
import config
from PIL import Image, ImageEnhance, ImageDraw
from stage_1 import scan_videos, create_metadata_for_video, create_frame_candidates
from stage_2 import select_thumbnail

STYLE_BLUE = "blue"
STYLE_PURPLE = "purple"
STYLE_WHITE = "white"

BAR_STYLES = {
    STYLE_BLUE: {
        "start": (0, 100, 220, 230),  # Deeper blue
        "end": (0, 190, 255, 230),  # Cyan-blue
    },
    STYLE_PURPLE: {
        "start": (40, 10, 60, 230),  # Dark Indigo
        "end": (100, 30, 110, 230),  # Deep Purple
    },
    STYLE_WHITE: {
        "start": (220, 220, 220, 240),  # Light Grey
        "end": (255, 255, 255, 240),  # Bright White
    },
}


def enhance_image_visuals(img_pil: Image.Image) -> Image.Image:
    # --- 1. Vibrancy & Contrast ---
    # Boost Color (1.5x is usually the sweet spot for sports)
    enhancer_color = ImageEnhance.Color(img_pil)
    img_pil = enhancer_color.enhance(1.5)

    # Boost Contrast slightly (1.1x)
    enhancer_contrast = ImageEnhance.Contrast(img_pil)
    img_pil = enhancer_contrast.enhance(1.05)

    enhancer_brightness = ImageEnhance.Brightness(img_pil)
    img_pil = enhancer_brightness.enhance(1.15)

    # --- 2. Vignette (Darkened Corners) ---
    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size

    x = np.linspace(-1, 1, width)
    y = np.linspace(-1, 1, height)
    X, Y = np.meshgrid(x, y)

    radius = np.sqrt(X**2 + Y**2)

    mask = np.clip(radius - 0.65, 0, 1)

    vignette_intensity = 140
    alpha_channel = (mask * vignette_intensity).astype(np.uint8)

    black_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    black_layer.putalpha(Image.fromarray(alpha_channel, mode="L"))

    final_img = Image.alpha_composite(img_pil, black_layer)

    return final_img.convert("RGB")


def draw_background_bar(
    img_pil: Image.Image, style_name: str = STYLE_BLUE
) -> Image.Image:
    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size

    style = BAR_STYLES.get(style_name, BAR_STYLES[STYLE_BLUE])
    color_start = style["start"]
    color_end = style["end"]

    # How tall should the bar be relative to image height? (e.g., 18%)
    bar_height_ratio = 0.18
    bar_height = int(height * bar_height_ratio)
    bar_top_y = height - bar_height

    gradient_bar = Image.new("RGBA", (width, bar_height), color=0)
    draw = ImageDraw.Draw(gradient_bar)

    for x in range(width):
        t = x / (width - 1) if width > 1 else 0

        r = int(color_start[0] * (1 - t) + color_end[0] * t)
        g = int(color_start[1] * (1 - t) + color_end[1] * t)
        b = int(color_start[2] * (1 - t) + color_end[2] * t)
        a = int(color_start[3] * (1 - t) + color_end[3] * t)

        draw.line([(x, 0), (x, bar_height)], fill=(r, g, b, a))

    overlay = Image.new("RGBA", img_pil.size, (0, 0, 0, 0))
    overlay.paste(gradient_bar, (0, bar_top_y))
    final_img = Image.alpha_composite(img_pil, overlay)

    return final_img.convert("RGB")


def render_thumbnail(video_folder: Path):
    selected_path = video_folder / "selected.jpg"
    metadata_path = video_folder / "metadata.json"
    output_path = video_folder / "thumbnail.jpg"

    if not selected_path.exists() or not metadata_path.exists():
        print(f"Missing selected thumbnail or metadata in {video_folder.name}")
        return

    img = Image.open(selected_path)
    img = enhance_image_visuals(img)
    img = draw_background_bar(img, STYLE_WHITE)
    img.save(output_path, quality=95)

    print(f"Rendered thumbnail saved to {output_path}")


if __name__ == "__main__":
    videos = list(scan_videos(config.INPUT_DIR))

    for video_file in videos:
        create_metadata_for_video(video_file)
        create_frame_candidates(video_file)

    for video_file in videos:
        select_thumbnail(video_file)

    for video_file in videos:
        workspace_folder = config.INPUT_DIR / video_file.stem
        render_thumbnail(workspace_folder)
