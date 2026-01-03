import textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
from thumbnail_enhancement.common import (
    enhance_image_visuals,
    format_team_name,
    get_theme_for_tournament,
)
from utils import get_metadata, get_selected_candidate_path, get_thumbnail_path
from logger import get_logger
from custom_exceptions import MissingThumbnailDataError

logger = get_logger(__name__)

# --- Configuration ---
SIDEBAR_RATIO = 0.3  # 30% Width
LOGO_PATH = Path("assets/logo.png")
FONT_PATH = Path("assets/Montserrat-ExtraBold.ttf")

# --- Colors ---
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)

# Sidebar Background Options
SIDEBAR_STYLES = {
    "blue": {
        "bg": (0, 60, 150),  # Deep Navy
        "text_main": (255, 255, 255),
        "tournament_color": (255, 255, 255),
    },
    "purple": {
        "bg": (40, 10, 60),  # Deep Purple
        "text_main": (255, 255, 255),
        "tournament_color": (255, 255, 255),
    },
    "white": {
        "bg": (240, 240, 240),  # Light Grey/White
        "text_main": (0, 0, 0),  # Black Text for contrast
        "tournament_color": (0, 0, 0),
    },
}


def get_font(size: int):
    try:
        return ImageFont.truetype(str(FONT_PATH), size)
    except OSError:
        return ImageFont.load_default()


def draw_sidebar_background(
    sidebar_w: int, canvas_h: int, style_key: str
) -> Image.Image:
    style = SIDEBAR_STYLES[style_key]
    sidebar = Image.new("RGB", (sidebar_w, canvas_h), style["bg"])
    return sidebar


def add_logo_to_sidebar(
    sidebar: Image.Image, sidebar_w: int, canvas_h: int
) -> tuple[int, int]:
    if not LOGO_PATH.exists():
        return (int(sidebar_w * 0.1), 50)

    logo = Image.open(LOGO_PATH).convert("RGBA")
    logo_w = int(sidebar_w * 0.4)
    aspect = logo.height / logo.width
    logo_h = int(logo_w * aspect)
    logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

    logo_x = int(sidebar_w * 0.1)
    logo_y = int(canvas_h * 0.05)

    sidebar.paste(logo, (logo_x, logo_y), logo)
    return (logo_x, logo_y + logo_h)


def draw_tournament_name(
    sidebar: Image.Image,
    tournament_name: str,
    sidebar_w: int,
    logo_x: int,
    logo_bottom_y: int,
    style_key: str,
):
    """
    Draws tournament name, handling wrapping (max 2 lines) and auto-shrinking font.
    """
    draw = ImageDraw.Draw(sidebar)
    style = SIDEBAR_STYLES[style_key]

    text = tournament_name.upper() if tournament_name else "TOURNAMENT"

    # 1. Define Constraints
    # Max width = Sidebar width - Left Padding (logo_x) - Right Padding (5%)
    max_text_width = sidebar_w - logo_x - int(sidebar_w * 0.05)
    max_lines = 2

    # Initial Font Config
    font_size = int(sidebar_w * 0.16)
    min_font_size = 20

    # 2. Logic to find best fit (Font Size & Line Split)
    final_lines = [text]
    final_font = get_font(font_size)

    # Helper to check if a list of lines fits the width
    def check_fits(lines, font):
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font)
            if (bbox[2] - bbox[0]) > max_text_width:
                return False
        return True

    # Iteratively reduce font size until it fits
    while font_size >= min_font_size:
        font = get_font(font_size)

        # Try 1 Line
        if check_fits([text], font):
            final_lines = [text]
            final_font = font
            break

        # Try 2 Lines (Wrap text)
        # Wrap roughly by character count to balance lines
        avg_char = len(text) // 2
        wrapped_lines = textwrap.wrap(text, width=max(10, avg_char))

        # Force max 2 lines (join the rest if longer)
        if len(wrapped_lines) > max_lines:
            wrapped_lines = wrapped_lines[:max_lines]
            wrapped_lines[-1] += "..."  # Add ellipsis if we truncated really long text

        if check_fits(wrapped_lines, font):
            final_lines = wrapped_lines
            final_font = font
            break

        # If neither fits, shrink font and try again
        font_size -= 2

    # 3. Draw Lines
    current_y = logo_bottom_y + 30
    line_height = final_font.getbbox("A")[3] + 10  # Height + spacing

    for line in final_lines:
        draw.text(
            (logo_x, current_y),
            line,
            font=final_font,
            fill=style["tournament_color"],
            anchor="la",
        )
        current_y += line_height


def draw_semi_pill_text(draw, x, y, width, height, text, bg_color, text_color):
    """
    Draws a semi-pill bar with Left-Aligned text.
    """
    # 1. Draw the Background Shape
    radius = height // 2

    # Body (Rectangle)
    draw.rectangle([(x, y), (x + width - radius + 1, y + height)], fill=bg_color)

    # Right Cap (Circle)
    circle_x1 = x + width - height
    circle_y1 = y
    circle_x2 = x + width
    circle_y2 = y + height
    draw.ellipse([(circle_x1, circle_y1), (circle_x2, circle_y2)], fill=bg_color)

    # 2. Draw the Text (Left Aligned)
    # UPDATE: Increased font size ratio from 0.55 to 0.75
    font_size = int(height * 0.75)
    font = get_font(font_size)

    # Text Padding (Left indent)
    # This must match the padding used in width calculations
    text_padding_left = int(height * 0.5)

    text_x = x + text_padding_left
    center_y = y + height / 2

    # Anchor 'lm' = Left Middle
    draw.text((text_x, center_y), text, font=font, fill=text_color, anchor="lm")


def draw_transparent_vs(draw, x, y, size, bg_color):
    font = get_font(size)
    stroke_width = max(2, int(size * 0.02))

    if bg_color == (240, 240, 240):
        fill_color = bg_color
        stroke_color = (0, 0, 0)
    else:
        fill_color = bg_color
        stroke_color = (255, 255, 255)

    draw.text(
        (x, y),
        "VS",
        font=font,
        fill=fill_color,
        stroke_width=stroke_width,
        stroke_fill=stroke_color,
        anchor="lm",
    )


def draw_matchup_block(
    final_img: Image.Image,
    team1_text: str,
    team2_text: str,
    sidebar_w: int,
    canvas_w: int,
    canvas_h: int,
    style_key: str,
):
    draw = ImageDraw.Draw(final_img)
    style = SIDEBAR_STYLES[style_key]

    # Configuration
    block_start_y = int(canvas_h * 0.6)
    pill_height = int(canvas_h * 0.11)
    pill_x = 0

    text_pad_left = int(pill_height * 0.5)
    text_pad_right = int(pill_height * 1.5)

    # --- 1. Calculate Sizes & Widths ---
    # Pill Font
    pill_font_size = int(pill_height * 0.75)
    pill_font = get_font(pill_font_size)

    # VS Font & Height Calculation
    vs_font_size = int(pill_height * 1.4)
    vs_font = get_font(vs_font_size)

    # Measure exact visual height of "VS"
    vs_bbox = draw.textbbox((0, 0), "VS", font=vs_font)
    vs_text_height = vs_bbox[3] - vs_bbox[1]

    # Minimum width
    min_width = sidebar_w + int(canvas_w * 0.05)

    # Calculate Team 1 Width
    bbox1 = draw.textbbox((0, 0), team1_text, font=pill_font)
    w1 = bbox1[2] - bbox1[0]
    pill_width_1 = max(min_width, w1 + text_pad_left + text_pad_right)

    # Calculate Team 2 Width
    bbox2 = draw.textbbox((0, 0), team2_text, font=pill_font)
    w2 = bbox2[2] - bbox2[0]
    pill_width_2 = max(min_width, w2 + text_pad_left + text_pad_right)

    # --- 2. Draw Elements ---

    # A. Draw VS FIRST (Sitting in the gap)
    vs_x = pill_x + text_pad_left

    # We want the VS to be centered in the gap, but we are about to shrink the gap.
    # Let's calculate the visual center based on the tighter spacing.
    # Gap scale factor: 0.x means we only use x0% of the VS height as spacing
    gap_scale = 0.9
    effective_gap = int(vs_text_height * gap_scale)

    # Center VS vertically between the bottom of T1 and top of T2
    t1_bottom = block_start_y + pill_height
    vs_center_y = t1_bottom + (effective_gap / 2)

    draw_transparent_vs(draw, vs_x, vs_center_y, vs_font_size, style["bg"])

    # B. Draw Team 1 Block
    draw_semi_pill_text(
        draw,
        pill_x,
        block_start_y,
        pill_width_1,
        pill_height,
        team1_text,
        COLOR_BLACK,
        COLOR_WHITE,
    )

    # C. Draw Team 2 Block
    # UPDATE: We use the reduced 'effective_gap' instead of full vs_text_height
    t2_y = block_start_y + pill_height + effective_gap

    draw_semi_pill_text(
        draw,
        pill_x,
        t2_y,
        pill_width_2,
        pill_height,
        team2_text,
        COLOR_BLACK,
        COLOR_WHITE,
    )


def prepare_image_side(selected_path: Path, image_w: int, canvas_h: int) -> Image.Image:
    raw_img = Image.open(selected_path).convert("RGB")
    enhanced_img = enhance_image_visuals(raw_img)
    return ImageOps.fit(
        enhanced_img, (image_w, canvas_h), method=Image.Resampling.LANCZOS
    )


def render_thumbnail(video_path: Path) -> str:
    selected_path = get_selected_candidate_path(video_path)
    output_path = get_thumbnail_path(video_path)
    metadata = get_metadata(video_path)

    if not selected_path.exists() or not metadata:
        raise MissingThumbnailDataError(
            f"Missing required data for {video_path.name} either selected thumbnail or metadata"
        )

    CANVAS_W, CANVAS_H = 1920, 1080
    final_img = Image.new("RGB", (CANVAS_W, CANVAS_H), COLOR_BLACK)

    sidebar_w = int(CANVAS_W * SIDEBAR_RATIO)
    image_w = CANVAS_W - sidebar_w

    # 1. Prepare and Paste Right Image
    right_img = prepare_image_side(selected_path, image_w, CANVAS_H)
    final_img.paste(right_img, (sidebar_w, 0))

    tournament = metadata.tournament.strip()
    style_key = get_theme_for_tournament(tournament)

    # 2. Prepare and Paste Sidebar Background & Text
    sidebar = draw_sidebar_background(sidebar_w, CANVAS_H, style_key)
    logo_x, logo_bottom_y = add_logo_to_sidebar(sidebar, sidebar_w, CANVAS_H)
    draw_tournament_name(
        sidebar, tournament, sidebar_w, logo_x, logo_bottom_y, style_key
    )
    final_img.paste(sidebar, (0, 0))

    # 3. Draw Matchup Block ON TOP of everything
    team1_names = metadata.team1_names
    team2_names = metadata.team2_names
    team1_text = format_team_name(team1_names)
    team2_text = format_team_name(team2_names)

    draw_matchup_block(
        final_img, team1_text, team2_text, sidebar_w, CANVAS_W, CANVAS_H, style_key
    )

    final_img.save(output_path, quality=95)
    return str(output_path)
