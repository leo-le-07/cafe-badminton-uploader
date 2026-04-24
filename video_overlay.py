import json
import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
import utils
from logger import get_logger

logger = get_logger(__name__)

FONT_PATH = Path("assets/Anton-Regular.ttf")
OVERLAY_DURATION = 12

COLOR_YELLOW = (255, 215, 0, 255)
COLOR_WHITE = (255, 255, 255, 255)
COLOR_RED_SHADOW = (204, 0, 0, 255)
COLOR_TRANSPARENT = (0, 0, 0, 0)

HALFTONE_DOT_RADIUS = 3
HALFTONE_SPACING = 9


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _measure_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _find_font_size_for_width(draw: ImageDraw.ImageDraw, text: str, target_width: int) -> int:
    size = 10
    while True:
        font = _get_font(size + 10)
        w, _ = _measure_text(draw, text, font)
        if w >= target_width:
            break
        size += 10
    while size > 1:
        font = _get_font(size)
        w, _ = _measure_text(draw, text, font)
        if w <= target_width:
            break
        size -= 1
    return size


def _draw_halftone_on_text(canvas: Image.Image, text: str, x: int, y: int, font: ImageFont.FreeTypeFont, dot_color: tuple) -> None:
    """Draws a halftone dot pattern over the area occupied by `text` at (x, y)."""
    tmp = Image.new("L", canvas.size, 0)
    tmp_draw = ImageDraw.Draw(tmp)
    tmp_draw.text((x, y), text, font=font, fill=255)

    dots = Image.new("RGBA", canvas.size, COLOR_TRANSPARENT)
    dots_draw = ImageDraw.Draw(dots)
    for py in range(0, canvas.height, HALFTONE_SPACING):
        for px in range(0, canvas.width, HALFTONE_SPACING):
            if tmp.getpixel((px, py)) > 128:
                dots_draw.ellipse(
                    [px - HALFTONE_DOT_RADIUS, py - HALFTONE_DOT_RADIUS,
                     px + HALFTONE_DOT_RADIUS, py + HALFTONE_DOT_RADIUS],
                    fill=dot_color,
                )

    canvas.alpha_composite(dots)


def _draw_word_with_shadow(
    canvas: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
    shadow_color: tuple,
    shadow_offset: int = 8,
    halftone_color: tuple | None = None,
) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.text((x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color)
    draw.text((x, y), text, font=font, fill=fill)
    if halftone_color:
        _draw_halftone_on_text(canvas, text, x, y, font, halftone_color)


def render_cafe_game_overlay(width: int, height: int) -> Image.Image:
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Font not found: {FONT_PATH}. Download Anton-Regular.ttf from Google Fonts.")

    canvas = Image.new("RGBA", (width, height), COLOR_TRANSPARENT)
    probe_draw = ImageDraw.Draw(canvas)

    target_width = int(width * 0.35)
    font_size = _find_font_size_for_width(probe_draw, "GAME", target_width)
    font = _get_font(font_size)

    cafe_w, cafe_h = _measure_text(probe_draw, "CAFE", font)
    game_w, game_h = _measure_text(probe_draw, "GAME", font)
    line_gap = int(font_size * 0.08)
    block_h = cafe_h + line_gap + game_h

    cafe_x = int(width * 0.07)
    game_x = int(width * 0.07)
    block_y = int(height * 0.10)
    game_y = block_y + cafe_h + line_gap

    _draw_word_with_shadow(
        canvas, "CAFE", cafe_x, block_y, font,
        fill=COLOR_YELLOW,
        shadow_color=COLOR_RED_SHADOW,
    )
    _draw_word_with_shadow(
        canvas, "GAME", game_x, game_y, font,
        fill=COLOR_WHITE,
        shadow_color=COLOR_RED_SHADOW,
    )

    return canvas


def render_thanks_overlay(width: int, height: int) -> Image.Image:
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Font not found: {FONT_PATH}. Download Anton-Regular.ttf from Google Fonts.")

    target_width = int(width * 0.70)
    tmp_canvas = Image.new("RGBA", (width, height), COLOR_TRANSPARENT)
    probe_draw = ImageDraw.Draw(tmp_canvas)

    font_size = _find_font_size_for_width(probe_draw, "THANKS FOR", target_width)
    font = _get_font(font_size)

    line1, line2 = "THANKS FOR", "WATCHING"
    l1_w, l1_h = _measure_text(probe_draw, line1, font)
    l2_w, l2_h = _measure_text(probe_draw, line2, font)
    line_gap = int(font_size * 0.08)
    block_w = max(l1_w, l2_w)
    block_h = l1_h + line_gap + l2_h

    text_canvas = Image.new("RGBA", (block_w + 40, block_h + 40), COLOR_TRANSPARENT)
    text_draw = ImageDraw.Draw(text_canvas)
    text_draw.text(((block_w - l1_w) // 2, 0), line1, font=font, fill=COLOR_WHITE)
    text_draw.text(((block_w - l2_w) // 2, l1_h + line_gap), line2, font=font, fill=COLOR_WHITE)

    rotated = text_canvas.rotate(-10, expand=True, resample=Image.Resampling.BICUBIC)

    canvas = Image.new("RGBA", (width, height), COLOR_TRANSPARENT)
    paste_x = (width - rotated.width) // 2
    paste_y = (height - rotated.height) // 2
    canvas.alpha_composite(rotated, dest=(paste_x, paste_y))

    return canvas


def get_video_dimensions(video_path: str) -> tuple[int, int]:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams",
         "-select_streams", "v:0", video_path],
        capture_output=True, check=True,
    )
    info = json.loads(result.stdout)
    stream = info["streams"][0]
    return int(stream["width"]), int(stream["height"])


def _get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", video_path],
        capture_output=True, check=True,
    )
    return float(json.loads(result.stdout)["format"]["duration"])


def _run_ffmpeg_overlay(
    video_path: str,
    cafe_png: str,
    thanks_png: str | None,
    thanks_start: float,
    output_path: str,
    use_hardware: bool,
    logo_path: str | None = None,
    logo_size: int | None = None,
) -> subprocess.CompletedProcess:
    encoder_args = ["-c:v", "h264_videotoolbox"] if use_hardware else ["-c:v", "libx264", "-preset", "ultrafast"]

    inputs = ["-i", video_path, "-i", cafe_png]
    if thanks_png:
        inputs += ["-i", thanks_png]
    if logo_path:
        inputs += ["-i", logo_path]

    logo_idx = (2 if not thanks_png else 3)

    if thanks_png:
        text_chain = (
            f"[0:v][1:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='lte(t,{OVERLAY_DURATION})'[v1];"
            f"[v1][2:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='gte(t,{thanks_start:.3f})'[v2]"
        )
    else:
        text_chain = (
            f"[0:v][1:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='lte(t,{OVERLAY_DURATION})'[v2]"
        )

    if logo_path and logo_size:
        filter_complex = (
            f"{text_chain};"
            f"[{logo_idx}:v]scale={logo_size}:-1,format=rgba[logo];"
            f"[v2][logo]overlay=x=main_w-overlay_w-20:y=20[out]"
        )
    else:
        filter_complex = text_chain.replace("[v2]", "[out]")

    cmd = (
        ["ffmpeg", "-y"]
        + inputs
        + ["-filter_complex", filter_complex, "-map", "[out]", "-map", "0:a"]
        + encoder_args
        + ["-c:a", "copy", output_path]
    )

    return subprocess.run(cmd, capture_output=True)


def add_video_overlays(video_path: str, output_path: str | None = None) -> str:
    if not FONT_PATH.exists():
        raise FileNotFoundError(f"Font not found: {FONT_PATH}. Download Anton-Regular.ttf from Google Fonts.")

    path = Path(video_path)

    if output_path is None:
        resolved_output = utils.get_processed_video_path(path)
    else:
        resolved_output = Path(output_path)

    if resolved_output.exists():
        logger.info(f"Processed video already exists, skipping: {resolved_output}")
        return str(resolved_output)

    resolved_output.parent.mkdir(parents=True, exist_ok=True)

    width, height = get_video_dimensions(video_path)
    duration = _get_video_duration(video_path)

    cafe_img = render_cafe_game_overlay(width, height)
    thanks_img = render_thanks_overlay(width, height) if duration > 24 else None
    thanks_start = duration - OVERLAY_DURATION

    logo_path = str(config.LOGO_PATH) if config.LOGO_PATH.exists() else None
    logo_size = int(width * 0.1) if logo_path else None
    if not logo_path:
        logger.warning(f"Logo not found at {config.LOGO_PATH}, skipping watermark")

    with tempfile.TemporaryDirectory() as tmp_dir:
        cafe_png = str(Path(tmp_dir) / "cafe_overlay.png")
        cafe_img.save(cafe_png)

        thanks_png = None
        if thanks_img is not None:
            thanks_png = str(Path(tmp_dir) / "thanks_overlay.png")
            thanks_img.save(thanks_png)

        result = _run_ffmpeg_overlay(video_path, cafe_png, thanks_png, thanks_start, str(resolved_output), use_hardware=True, logo_path=logo_path, logo_size=logo_size)

        if result.returncode != 0:
            logger.warning("Hardware encoder failed, retrying with libx264...")
            result = _run_ffmpeg_overlay(video_path, cafe_png, thanks_png, thanks_start, str(resolved_output), use_hardware=False, logo_path=logo_path, logo_size=logo_size)

        if result.returncode != 0:
            raise RuntimeError(
                f"FFmpeg failed with code {result.returncode}:\n{result.stderr.decode()}"
            )

    logger.info(f"Video overlays applied: {resolved_output}")
    return str(resolved_output)
