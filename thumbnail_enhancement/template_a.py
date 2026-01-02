from pathlib import Path

import random
from PIL import Image, ImageDraw, ImageFont

from thumbnail_enhancement.common import (
    LOGO_PATH,
    STYLE_BLUE,
    STYLE_PURPLE,
    STYLE_WHITE,
    add_logo,
    enhance_image_visuals,
    format_matchup_text,
    get_theme_for_tournament,
)
from utils import get_metadata, get_selected_candidate_path, get_thumbnail_path

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

BAR_HEIGHT_RATIO = 0.18

FONT_PATH = Path("assets/Montserrat-ExtraBold.ttf")


def draw_background_bar(
    img_pil: Image.Image, style_name: str = STYLE_BLUE
) -> Image.Image:
    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size

    style = BAR_STYLES.get(style_name, BAR_STYLES[STYLE_BLUE])
    color_start = style["start"]
    color_end = style["end"]

    bar_height = int(height * BAR_HEIGHT_RATIO)
    bar_top_y = height - bar_height

    cols = 10
    rows = 2
    cell_w = width / cols
    cell_h = bar_height / rows

    vertices = []
    for r in range(rows + 1):
        row_points = []
        for c in range(cols + 1):
            x = c * cell_w
            y = r * cell_h

            if 0 < c < cols and 0 < r < rows:
                x += random.uniform(-cell_w * 0.3, cell_w * 0.3)
                y += random.uniform(-cell_h * 0.3, cell_h * 0.3)

            row_points.append((x, y))
        vertices.append(row_points)

    poly_bar = Image.new("RGBA", (width, bar_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(poly_bar)

    for r in range(rows):
        for c in range(cols):
            p1 = vertices[r][c]
            p2 = vertices[r][c + 1]
            p3 = vertices[r + 1][c + 1]
            p4 = vertices[r + 1][c]

            center_x = (p1[0] + p2[0]) / 2
            t = center_x / width

            red = int(color_start[0] * (1 - t) + color_end[0] * t)
            green = int(color_start[1] * (1 - t) + color_end[1] * t)
            blue = int(color_start[2] * (1 - t) + color_end[2] * t)
            alpha = int(color_start[3] * (1 - t) + color_end[3] * t)

            noise_intensity = 25

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

            draw.polygon([p1, p2, p4], fill=color1)
            draw.polygon([p2, p3, p4], fill=color2)

    overlay = Image.new("RGBA", img_pil.size, (0, 0, 0, 0))
    overlay.paste(poly_bar, (0, bar_top_y))
    final_img = Image.alpha_composite(img_pil, overlay)

    return final_img.convert("RGB")


def draw_matchup_text(img_pil: Image.Image, text: str, style_name: str) -> Image.Image:
    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size
    draw = ImageDraw.Draw(img_pil)

    style = BAR_STYLES.get(style_name, BAR_STYLES[STYLE_BLUE])
    text_color = style["text_color"]

    bar_height = int(height * BAR_HEIGHT_RATIO)
    center_y = height - (bar_height / 2)
    center_x = width / 2

    font_size = int(bar_height * 0.6)

    try:
        font = ImageFont.truetype(str(FONT_PATH), font_size)
    except OSError:
        print(f"Warning: Could not load font at {FONT_PATH}. Using default.")
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]

    max_width = width * 0.90

    while text_width > max_width and font_size > 10:
        font_size -= 2
        try:
            font = ImageFont.truetype(str(FONT_PATH), font_size)
        except OSError:
            break
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]

    shadow_color = (0, 0, 0, 100)
    draw.text(
        (center_x + 3, center_y + 3), text, font=font, fill=shadow_color, anchor="mm"
    )

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

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    badge_pad_x = int(font_size * 0.6)
    badge_pad_y = int(font_size * 0.3)

    badge_w = int(text_w + (badge_pad_x * 2))
    badge_h = int(text_h + (badge_pad_y * 2))

    tip_depth = int(badge_h / 2)
    total_badge_w = badge_w + tip_depth

    badge_gradient = Image.new("RGBA", (total_badge_w, badge_h), color=0)
    draw_grad = ImageDraw.Draw(badge_gradient)

    for x in range(total_badge_w):
        t = x / (total_badge_w - 1) if total_badge_w > 1 else 0
        r = int(color_start[0] * (1 - t) + color_end[0] * t)
        g = int(color_start[1] * (1 - t) + color_end[1] * t)
        b = int(color_start[2] * (1 - t) + color_end[2] * t)
        a = int(color_start[3] * (1 - t) + color_end[3] * t)
        draw_grad.line([(x, 0), (x, badge_h)], fill=(r, g, b, a))

    mask = Image.new("L", (total_badge_w, badge_h), 0)
    draw_mask = ImageDraw.Draw(mask)

    points = [
        (0, 0),
        (0, badge_h),
        (total_badge_w - tip_depth, badge_h),
        (total_badge_w, int(badge_h / 2)),
        (total_badge_w - tip_depth, 0),
    ]
    draw_mask.polygon(points, fill=255)

    x1 = 0
    y1 = padding
    img_pil.paste(badge_gradient, (x1, y1), mask)

    rectangular_part_w = total_badge_w - tip_depth
    text_x = x1 + (rectangular_part_w / 2)
    text_y = y1 + (badge_h / 2)

    draw.text((text_x, text_y), text, font=font, fill=text_color, anchor="mm")

    return img_pil.convert("RGB")


def render_thumbnail(video_path: Path):
    selected_path = get_selected_candidate_path(video_path)
    output_path = get_thumbnail_path(video_path)
    metadata = get_metadata(video_path)

    if not selected_path.exists() or not metadata:
        print(f"Missing selected thumbnail or metadata in {video_path.name}")
        return

    team_1_names = metadata.team1_names
    team_2_names = metadata.team2_names
    matchup_text = format_matchup_text(team_1_names, team_2_names)
    tournament = metadata.tournament.strip()
    decor_style = get_theme_for_tournament(tournament)

    img = Image.open(selected_path)
    img = enhance_image_visuals(img)
    img = draw_background_bar(img, decor_style)
    img = draw_matchup_text(img, matchup_text, decor_style)
    img = add_logo(img, LOGO_PATH)
    img = draw_tournament_badge(img, tournament, decor_style)

    img.save(output_path, quality=95)

    print(f"{output_path}")
