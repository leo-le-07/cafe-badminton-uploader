from pathlib import Path

import numpy as np
import random
import config
from PIL import Image, ImageEnhance, ImageDraw, ImageFont

from utils import (
    get_thumbnail_path,
    scan_videos,
    get_metadata,
    get_selected_candidate_path,
)

STYLE_BLUE = "blue"
STYLE_PURPLE = "purple"
STYLE_WHITE = "white"

BAR_STYLES = {
    STYLE_BLUE: {
        "start": (0, 60, 150, 240),
        "end": (0, 140, 230, 240),
        "text_color": (255, 255, 255, 255),
    },
    STYLE_PURPLE: {
        "start": (40, 10, 60, 230),
        "end": (100, 30, 110, 230),
        "text_color": (255, 255, 255, 255),
    },
    STYLE_WHITE: {
        "start": (220, 220, 220, 240),
        "end": (255, 255, 255, 240),
        "text_color": (20, 20, 20, 255),
    },
}

BAR_HEIGHT_RATIO = 0.18 # 18% of image height

RECOGNIZED_TOURNAMENTS = {
    "cafe game": STYLE_BLUE,
    "friendly game": STYLE_WHITE,
    "tournament": STYLE_PURPLE,
}

DEFAULT_THEME = STYLE_BLUE

LOGO_PATH = Path("assets/logo.png")
FONT_PATH = Path("assets/Montserrat-ExtraBold.ttf")


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
    """
    Draws a low-poly (faceted crystal) background bar instead of a simple gradient.
    """
    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size

    # 1. Get Style Configuration
    style = BAR_STYLES.get(style_name, BAR_STYLES[STYLE_BLUE])
    color_start = style["start"]
    color_end = style["end"]

    # 2. Dimensions
    bar_height = int(height * BAR_HEIGHT_RATIO)
    bar_top_y = height - bar_height

    # 3. Low Poly Grid Settings
    # We create a grid of points and "jitter" them to make irregular triangles
    cols = 10  # Number of horizontal segments
    rows = 2  # Number of vertical segments
    cell_w = width / cols
    cell_h = bar_height / rows

    # Generate Grid Points
    vertices = []
    for r in range(rows + 1):
        row_points = []
        for c in range(cols + 1):
            # Base grid position
            x = c * cell_w
            y = r * cell_h

            # Add random "Jitter" to inner points to make it look organic
            # We don't jitter the edges so the bar stays a perfect rectangle
            if 0 < c < cols and 0 < r < rows:
                x += random.uniform(-cell_w * 0.3, cell_w * 0.3)
                y += random.uniform(-cell_h * 0.3, cell_h * 0.3)

            row_points.append((x, y))
        vertices.append(row_points)

    # 4. Draw Triangles onto a separate layer
    poly_bar = Image.new("RGBA", (width, bar_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(poly_bar)

    for r in range(rows):
        for c in range(cols):
            # Get the 4 points of the grid cell
            p1 = vertices[r][c]  # Top-Left
            p2 = vertices[r][c + 1]  # Top-Right
            p3 = vertices[r + 1][c + 1]  # Bottom-Right
            p4 = vertices[r + 1][c]  # Bottom-Left

            # Calculate base color based on horizontal position (Gradient logic)
            center_x = (p1[0] + p2[0]) / 2
            t = center_x / width  # 0.0 to 1.0

            # Interpolate between start and end color
            red = int(color_start[0] * (1 - t) + color_end[0] * t)
            green = int(color_start[1] * (1 - t) + color_end[1] * t)
            blue = int(color_start[2] * (1 - t) + color_end[2] * t)
            alpha = int(color_start[3] * (1 - t) + color_end[3] * t)

            # --- The "Low Poly" Magic: Randomize Brightness ---
            # We create two slightly different colors for the two triangles in the square
            noise_intensity = 25  # How much the color varies (facet effect)

            # Helper to add noise safely
            def get_faceted_color(r, g, b, a, noise):
                n = random.randint(-noise, noise)
                return (
                    max(0, min(255, r + n)),
                    max(0, min(255, g + n)),
                    max(0, min(255, b + n)),
                    a,
                )

            color1 = get_faceted_color(red, green, blue, alpha, noise_intensity)
            color2 = get_faceted_color(red, green, blue, alpha, noise_intensity)

            # Draw two triangles to fill the cell
            # Triangle 1 (Top-Left, Top-Right, Bottom-Left)
            draw.polygon([p1, p2, p4], fill=color1)
            # Triangle 2 (Top-Right, Bottom-Right, Bottom-Left)
            draw.polygon([p2, p3, p4], fill=color2)

    # 5. Composite
    overlay = Image.new("RGBA", img_pil.size, (0, 0, 0, 0))
    overlay.paste(poly_bar, (0, bar_top_y))
    final_img = Image.alpha_composite(img_pil, overlay)

    return final_img.convert("RGB")


def add_logo(img_pil: Image.Image, logo_path: Path) -> Image.Image:
    if not logo_path.exists():
        print(f"Logo file not found: {logo_path}")
        return img_pil

    img_pil = img_pil.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    # Resize Logo (Responsive: 10% of image width)
    target_width = int(img_pil.width * 0.10)
    aspect_ratio = logo.height / logo.width
    target_height = int(target_width * aspect_ratio)

    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)

    # Calculate Position (Top Right with Padding)
    padding = int(img_pil.width * 0.03)  # 3% padding from edges
    x = img_pil.width - target_width - padding
    y = padding

    # Paste (Using the logo itself as the alpha mask)stage3
    img_pil.paste(logo, (x, y), logo)

    return img_pil.convert("RGB")


def draw_matchup_text(img_pil: Image.Image, text: str, style_name: str) -> Image.Image:
    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size
    draw = ImageDraw.Draw(img_pil)

    # 1. Get Text Color based on Style
    style = BAR_STYLES.get(style_name, BAR_STYLES[STYLE_BLUE])
    text_color = style["text_color"]

    # 2. Calculate Text Area (Inside the bar)
    bar_height = int(height * BAR_HEIGHT_RATIO)
    # Center of the bar vertically
    center_y = height - (bar_height / 2)
    center_x = width / 2

    # 3. Dynamic Font Sizing
    # Start with a font size approx 60% of bar height
    font_size = int(bar_height * 0.6)

    try:
        font = ImageFont.truetype(str(FONT_PATH), font_size)
    except OSError:
        print(f"Warning: Could not load font at {FONT_PATH}. Using default.")
        font = ImageFont.load_default()

    # Measure text size
    # bbox gives (left, top, right, bottom)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]

    # Max allowed width (90% of screen width)
    max_width = width * 0.90

    # Shrink font until it fits
    while text_width > max_width and font_size > 10:
        font_size -= 2
        try:
            font = ImageFont.truetype(str(FONT_PATH), font_size)
        except OSError:
            break
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]

    # 4. Draw Text (Anchor 'mm' = Middle Middle)
    # We draw it twice: once as a shadow/outline for readability, then the main text

    # Shadow (Offset slightly) - Only needed if contrast is risky, but good for style
    shadow_color = (0, 0, 0, 100)  # Faint shadow
    draw.text(
        (center_x + 3, center_y + 3), text, font=font, fill=shadow_color, anchor="mm"
    )

    # Main Text
    draw.text((center_x, center_y), text, font=font, fill=text_color, anchor="mm")

    return img_pil.convert("RGB")


def draw_tournament_badge(
    img_pil: Image.Image, tournament_name: str, style_name: str
) -> Image.Image:
    if not tournament_name:
        return img_pil

    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size
    draw = ImageDraw.Draw(img_pil)

    # 1. Configuration from Style
    style = BAR_STYLES.get(style_name, BAR_STYLES[STYLE_BLUE])
    color_start = style["start"]
    color_end = style["end"]
    text_color = style["text_color"]

    padding = int(width * 0.03)
    font_size = int(width * 0.04)

    try:
        font = ImageFont.truetype(str(FONT_PATH), font_size)
    except OSError:
        font = ImageFont.load_default()

    text = tournament_name.upper()

    # 2. Calculate Badge Dimensions
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    badge_pad_x = int(font_size * 0.6)
    badge_pad_y = int(font_size * 0.3)

    # Force integer casting
    badge_w = int(text_w + (badge_pad_x * 2))
    badge_h = int(text_h + (badge_pad_y * 2))

    # --- NEW: Define Tag Shape Tip Depth ---
    # The depth of the pointy triangle tip. Half height looks proportional.
    tip_depth = int(badge_h / 2)
    # Add the tip depth to the overall width so the text area doesn't feel cramped
    total_badge_w = badge_w + tip_depth

    # 3. Create Gradient Badge (Off-screen canvas sized to total width)
    badge_gradient = Image.new("RGBA", (total_badge_w, badge_h), color=0)
    draw_grad = ImageDraw.Draw(badge_gradient)

    # Draw gradient across the full width
    for x in range(total_badge_w):
        t = x / (total_badge_w - 1) if total_badge_w > 1 else 0
        r = int(color_start[0] * (1 - t) + color_end[0] * t)
        g = int(color_start[1] * (1 - t) + color_end[1] * t)
        b = int(color_start[2] * (1 - t) + color_end[2] * t)
        a = int(color_start[3] * (1 - t) + color_end[3] * t)
        draw_grad.line([(x, 0), (x, badge_h)], fill=(r, g, b, a))

    # 4. Create Tag Polygon Mask
    mask = Image.new("L", (total_badge_w, badge_h), 0)
    draw_mask = ImageDraw.Draw(mask)

    # Define vertices for a tag shape pointing right:
    # Flat on left, pointed on right.
    points = [
        (0, 0),  # Top-Left
        (0, badge_h),  # Bottom-Left
        (total_badge_w - tip_depth, badge_h),  # Bottom-Right shoulder
        (total_badge_w, int(badge_h / 2)),  # The pointy tip
        (total_badge_w - tip_depth, 0),  # Top-Right shoulder
    ]
    # Draw filled white polygon on black mask
    draw_mask.polygon(points, fill=255)

    # 5. Composite Badge onto Main Image
    # x1 = 0 means it's flush with the left edge of the screen
    x1 = 0
    y1 = padding
    img_pil.paste(badge_gradient, (x1, y1), mask)

    # 6. Draw Text
    # Visually center the text in the rectangular part of the tag (ignoring the tip)
    rectangular_part_w = total_badge_w - tip_depth
    text_x = x1 + (rectangular_part_w / 2)
    text_y = y1 + (badge_h / 2)

    draw.text((text_x, text_y), text, font=font, fill=text_color, anchor="mm")

    return img_pil.convert("RGB")


def get_theme_for_tournament(tournament_name: str) -> str:
    if not tournament_name:
        return DEFAULT_THEME
    
    normalized = tournament_name.lower().strip()
    return RECOGNIZED_TOURNAMENTS.get(normalized, DEFAULT_THEME)


def render_thumbnail(video_path: Path):
    selected_path = get_selected_candidate_path(video_path)
    output_path = get_thumbnail_path(video_path)
    metadata = get_metadata(video_path)

    if not selected_path.exists() or not metadata:
        print(f"Missing selected thumbnail or metadata in {video_path.name}")
        return

    team_1_names = metadata.get("team1Names")
    team_2_names = metadata.get("team2Names")
    matchup_text = (
        f"{'/'.join(team_1_names).upper()} vs {'/'.join(team_2_names).upper()}"
    )
    tournament = metadata.get("tournament", "").strip()
    decor_style = get_theme_for_tournament(tournament)

    img = Image.open(selected_path)
    img = enhance_image_visuals(img)
    img = draw_background_bar(img, decor_style)
    img = draw_matchup_text(img, matchup_text, decor_style)
    img = add_logo(img, LOGO_PATH)
    img = draw_tournament_badge(img, tournament, decor_style)

    img.save(output_path, quality=95)

    print(f"{output_path}")


def run():
    videos = list(scan_videos(config.INPUT_DIR))

    for video_path in videos:
        render_thumbnail(video_path)


if __name__ == "__main__":
    run()
