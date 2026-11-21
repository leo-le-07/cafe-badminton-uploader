import os
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import config
import media_probe
from app.models import Segment
from logger import get_logger

logger = get_logger(__name__)

FONT_PATH = Path("assets/Anton-Regular.ttf")
OVERLAY_DURATION = 12
DEFAULT_FPS = 30.0
STDERR_TAIL_LINES = 15

COLOR_YELLOW = (255, 215, 0, 255)
COLOR_WHITE = (255, 255, 255, 255)
COLOR_RED_SHADOW = (204, 0, 0, 255)
COLOR_TRANSPARENT = (0, 0, 0, 0)

HALFTONE_DOT_RADIUS = 3
HALFTONE_SPACING = 9


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _measure_text(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont
) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _find_font_size_for_width(
    draw: ImageDraw.ImageDraw, text: str, target_width: int
) -> int:
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


def _draw_halftone_on_text(
    canvas: Image.Image,
    text: str,
    x: int,
    y: int,
    font: ImageFont.FreeTypeFont,
    dot_color: tuple,
) -> None:
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
                    [
                        px - HALFTONE_DOT_RADIUS,
                        py - HALFTONE_DOT_RADIUS,
                        px + HALFTONE_DOT_RADIUS,
                        py + HALFTONE_DOT_RADIUS,
                    ],
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
    draw.text(
        (x + shadow_offset, y + shadow_offset), text, font=font, fill=shadow_color
    )
    draw.text((x, y), text, font=font, fill=fill)
    if halftone_color:
        _draw_halftone_on_text(canvas, text, x, y, font, halftone_color)


def render_cafe_game_words(width: int, height: int) -> list[Image.Image]:
    """CAFE and GAME as two full-frame images, each word where it sits in the
    intro, so the render can animate them one after the other."""
    if not FONT_PATH.exists():
        raise FileNotFoundError(
            f"Font not found: {FONT_PATH}. Download Anton-Regular.ttf from Google Fonts."
        )

    probe_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font_size = _find_font_size_for_width(probe_draw, "GAME", int(width * 0.35))
    font = _get_font(font_size)

    _, cafe_h = _measure_text(probe_draw, "CAFE", font)
    line_gap = int(font_size * 0.08)
    x = int(width * 0.07)
    cafe_y = int(height * 0.10)
    game_y = cafe_y + cafe_h + line_gap

    words = []
    for text, y, fill in (
        ("CAFE", cafe_y, COLOR_YELLOW),
        ("GAME", game_y, COLOR_WHITE),
    ):
        canvas = Image.new("RGBA", (width, height), COLOR_TRANSPARENT)
        _draw_word_with_shadow(
            canvas, text, x, y, font, fill=fill, shadow_color=COLOR_RED_SHADOW
        )
        words.append(canvas)
    return words


def render_cafe_game_overlay(width: int, height: int) -> Image.Image:
    """The intro as one still image (both words in place)."""
    cafe, game = render_cafe_game_words(width, height)
    cafe.alpha_composite(game)
    return cafe


LOGO_CAPTION = "CAFE BADMINTON"


def render_logo_badge(logo_path: str, logo_width: int) -> Image.Image:
    """The watermark: the logo scaled to `logo_width`, with CAFE BADMINTON
    centred just under it. The caption is white with a dark outline so it
    reads on any background, and spans about the logo's width (a little
    wider on narrow logos so it stays legible)."""
    with Image.open(logo_path) as src:
        logo = src.convert("RGBA")
    logo = logo.resize(
        (logo_width, max(1, round(logo.height * logo_width / logo.width))),
        Image.Resampling.LANCZOS,
    )

    probe_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    text_width = max(logo_width, 140)
    font = _get_font(_find_font_size_for_width(probe_draw, LOGO_CAPTION, text_width))
    stroke = max(1, font.size // 12)
    left, top, right, bottom = probe_draw.textbbox(
        (0, 0), LOGO_CAPTION, font=font, stroke_width=stroke
    )
    gap = max(2, logo.height // 20)
    margin = stroke + 1  # keeps the outline's soft edge inside the image

    badge_w = max(logo.width, right - left + 2 * margin)
    badge = Image.new(
        "RGBA", (badge_w, logo.height + gap + bottom - top + margin), COLOR_TRANSPARENT
    )
    badge.alpha_composite(logo, dest=((badge_w - logo.width) // 2, 0))
    ImageDraw.Draw(badge).text(
        ((badge_w - (right - left)) // 2 - left, logo.height + gap - top),
        LOGO_CAPTION,
        font=font,
        fill=COLOR_WHITE,
        stroke_width=stroke,
        stroke_fill=(20, 20, 20, 255),
    )
    return badge


def _thanks_text_block(width: int) -> Image.Image:
    """THANKS FOR / WATCHING, centred, unrotated, with a transparent margin.

    Glyphs are drawn at their bounding box, not at the font's origin: Anton
    leaves a large gap above the letters, which pushed the second line past
    the bottom of the block."""
    probe_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    font_size = _find_font_size_for_width(probe_draw, "THANKS FOR", int(width * 0.70))
    font = _get_font(font_size)

    lines = ("THANKS FOR", "WATCHING")
    boxes = [probe_draw.textbbox((0, 0), line, font=font) for line in lines]
    line_gap = int(font_size * 0.08)
    pad = 20
    block_w = max(right - left for left, _, right, _ in boxes)
    block_h = sum(bottom - top for _, top, _, bottom in boxes) + line_gap

    block = Image.new("RGBA", (block_w + 2 * pad, block_h + 2 * pad), COLOR_TRANSPARENT)
    draw = ImageDraw.Draw(block)
    y = pad
    for line, (left, top, right, bottom) in zip(lines, boxes):
        x = pad + (block_w - (right - left)) // 2
        draw.text((x - left, y - top), line, font=font, fill=COLOR_WHITE)
        y += bottom - top + line_gap
    return block


def render_thanks_overlay(width: int, height: int) -> Image.Image:
    if not FONT_PATH.exists():
        raise FileNotFoundError(
            f"Font not found: {FONT_PATH}. Download Anton-Regular.ttf from Google Fonts."
        )

    rotated = _thanks_text_block(width).rotate(
        -10, expand=True, resample=Image.Resampling.BICUBIC
    )

    # Full-frame and centred, so scaling the whole image (the zoom-in in
    # build_render_command) grows the text from the centre of the video.
    canvas = Image.new("RGBA", (width, height), COLOR_TRANSPARENT)
    paste_x = (width - rotated.width) // 2
    paste_y = (height - rotated.height) // 2
    canvas.alpha_composite(rotated, dest=(paste_x, paste_y))

    return canvas


@dataclass(frozen=True)
class RenderInput:
    path: str
    start: float
    end: float
    has_audio: bool
    width: int
    height: int
    fps: float = DEFAULT_FPS  # of this segment's own source

    @property
    def duration(self) -> float:
        return self.end - self.start

    def seek_window(self) -> tuple[float, float]:
        """Input-side `-ss` and `-t` that keep exactly the frames shown at
        `start` up to, not including, the frame shown at `end`.

        Segment edges sit on the frame grid, where rounding the time puts the
        seek on either side of a frame's timestamp; seeking half a frame early
        keeps every edge between two frames."""
        half = 0.5 / (self.fps if self.fps > 0 else DEFAULT_FPS)
        return max(0.0, self.start - half), self.duration


def overlay_timing(total_duration: float) -> tuple[bool, float]:
    """Whether the outro overlay is shown and when it starts, in output time."""
    return total_duration > 2 * OVERLAY_DURATION, total_duration - OVERLAY_DURATION


_AUDIO_FORMAT = "aformat=sample_rates=48000:channel_layouts=stereo"

# THANKS FOR WATCHING zooms in from the centre: it starts at THANKS_ZOOM_FROM
# of its size, grows with a slight overshoot (ease-out-back) for
# THANKS_ZOOM_SECONDS, then holds; it also fades in over THANKS_FADE_SECONDS.
THANKS_ZOOM_SECONDS = 0.8
THANKS_ZOOM_FROM = 0.1
THANKS_FADE_SECONDS = 0.25
_OVERSHOOT = 1.02  # 1.70158 is the classic ease-out-back; this is gentler

# CAFE then GAME slide in from the left edge (ease-out-back,
# INTRO_SLIDE_SECONDS each, GAME INTRO_STAGGER_SECONDS later) and slide back
# out the same way, in the same order, over the end of the intro.
INTRO_SLIDE_SECONDS = 0.6
INTRO_STAGGER_SECONDS = 0.15
INTRO_SLIDE_FROM = 0.5  # off-screen: this fraction of the video width to the left


def _ease_out_back(progress: str) -> str:
    """ffmpeg expression easing `progress` (an expression in 0..1) with a
    slight overshoot. Commas are escaped for the filtergraph."""
    p = f"({progress}-1)"
    return f"(1+{_OVERSHOOT + 1:g}*pow({p}\\,3)+{_OVERSHOOT:g}*pow({p}\\,2))"


def _thanks_zoom_filter() -> str:
    """Filter for the looped thanks image: per-frame scale (`t` is the
    image's own time, 0 at the start of the outro) and an alpha fade-in."""
    ease = _ease_out_back(f"min(t/{THANKS_ZOOM_SECONDS}\\,1)")
    factor = f"({THANKS_ZOOM_FROM:g}+{1 - THANKS_ZOOM_FROM:g}*{ease})"
    return (
        "format=rgba,"
        f"scale=w='max(2\\,trunc(iw*{factor}/2)*2)'"
        f":h='max(2\\,trunc(ih*{factor}/2)*2)':eval=frame,"
        f"fade=t=in:st=0:d={THANKS_FADE_SECONDS:g}:alpha=1"
    )


def _intro_word_x(word: int) -> str:
    """Overlay x for intro word number `word` (0 = CAFE) at video time `t`:
    off-screen, slides in, holds, slides out. Its image is full-frame with the
    word already in place, so x is only the offset."""
    enter = word * INTRO_STAGGER_SECONDS
    leave = OVERLAY_DURATION - INTRO_SLIDE_SECONDS - INTRO_STAGGER_SECONDS + enter
    slide = f"{INTRO_SLIDE_SECONDS:g}"
    entered = _ease_out_back(f"clip((t-{enter:g})/{slide}\\,0\\,1)")
    # The exit is the entry played backwards (ease-in-back).
    stayed = _ease_out_back(f"(1-clip((t-{leave:g})/{slide}\\,0\\,1))")
    return f"-W*{INTRO_SLIDE_FROM:g}*((1-{entered})+(1-{stayed}))"


def build_render_command(
    inputs: list[RenderInput],
    cafe_pngs: list[str],
    thanks_png: str | None,
    thanks_start: float,
    logo_path: str | None,
    logo_size: int | None,
    output_path: str,
    use_hardware: bool,
    fps: float | None = None,
) -> list[str]:
    """One ffmpeg pass: trim each segment, normalise it to the first segment's
    size (and `fps` when given), concatenate, then burn in the overlays."""
    encoder_args = (
        ["-c:v", "h264_videotoolbox"]
        if use_hardware
        else ["-c:v", "libx264", "-preset", "ultrafast"]
    )
    width, height = inputs[0].width, inputs[0].height
    fps_filter = f",fps={fps:.10g}" if fps else ""

    args: list[str] = []
    chains: list[str] = []
    concat_pads = ""
    for i, inp in enumerate(inputs):
        seek, length = inp.seek_window()
        args += ["-ss", f"{seek:.6f}", "-t", f"{length:.6f}", "-i", inp.path]
        # The seek starts half a frame early; restart the timestamps at 0 so
        # the fps filter does not repeat the first frame to fill that gap.
        chains.append(
            f"[{i}:v]setpts=PTS-STARTPTS,scale={width}:{height},setsar=1{fps_filter}[v{i}]"
        )
        if inp.has_audio:
            chains.append(f"[{i}:a]asetpts=PTS-STARTPTS,{_AUDIO_FORMAT}[a{i}]")
        else:
            chains.append(
                f"anullsrc=r=48000:cl=stereo,atrim=duration={inp.duration:.6f},{_AUDIO_FORMAT}[a{i}]"
            )
        concat_pads += f"[v{i}][a{i}]"
    chains.append(f"{concat_pads}concat=n={len(inputs)}:v=1:a=1[cat][aout]")

    # The intro words are still images moved by overlay (which re-evaluates
    # x every frame and keeps showing a single-frame input), so they add no
    # frames of their own and never lengthen the video.
    idx = len(inputs) - 1
    last = "cat"
    for word, png in enumerate(cafe_pngs):
        idx += 1
        args += ["-i", png]
        chains.append(
            f"[{last}][{idx}:v]overlay=x='{_intro_word_x(word)}':y=0"
            f":enable='lte(t,{OVERLAY_DURATION})'[intro{word}]"
        )
        last = f"intro{word}"
    if thanks_png:
        idx += 1
        # Looped into a clip as long as the outro so it can be scaled and
        # faded frame by frame; its timestamps are then moved to the outro.
        # It is only used on videos longer than two overlays, so it never
        # outlasts the video.
        args += ["-loop", "1", "-framerate", f"{fps or DEFAULT_FPS:.10g}"]
        args += ["-t", f"{OVERLAY_DURATION}", "-i", thanks_png]
        chains.append(
            f"[{idx}:v]{_thanks_zoom_filter()},setpts=PTS+{thanks_start:.3f}/TB[thanks]"
        )
        chains.append(
            f"[{last}][thanks]overlay=x=(W-w)/2:y=(H-h)/2:enable='gte(t,{thanks_start:.3f})'[ov2]"
        )
        last = "ov2"
    if logo_path and logo_size:
        idx += 1
        args += ["-i", logo_path]
        chains.append(f"[{idx}:v]scale={logo_size}:-1,format=rgba[logo]")
        chains.append(f"[{last}][logo]overlay=x=main_w-overlay_w-20:y=20[ov3]")
        last = "ov3"

    return (
        ["ffmpeg", "-hide_banner", "-y", "-nostats", "-progress", "pipe:1"]
        + args
        + ["-filter_complex", ";".join(chains), "-map", f"[{last}]", "-map", "[aout]"]
        + encoder_args
        + ["-c:a", "aac", "-b:a", "192k", "-f", "mov", output_path]
    )


def _run_ffmpeg(
    cmd: list[str], total_duration: float, progress: Callable[[float], None] | None
) -> tuple[int, str]:
    """Runs ffmpeg, reporting percent done from `-progress` output. Returns
    (returncode, stderr)."""
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL, text=True
        )
        assert proc.stdout is not None
        try:
            with proc.stdout:
                for line in proc.stdout:
                    key, _, value = line.strip().partition("=")
                    if (
                        key == "out_time_us"
                        and progress
                        and value.lstrip("-").isdigit()
                        and total_duration > 0
                    ):
                        progress(
                            max(
                                0.0, min(100.0, int(value) / 1e6 / total_duration * 100)
                            )
                        )
        except BaseException:
            # Never leave ffmpeg running (and holding the sources) when the
            # caller aborts, e.g. a progress callback raising to cancel.
            proc.kill()
            proc.wait()
            raise
        returncode = proc.wait()
        err.seek(0)
        return returncode, err.read().decode(errors="replace")


def render_match(
    segments: list[Segment],
    source_dir: Path,
    output_path: Path,
    progress: Callable[[float], None] | None = None,
) -> str:
    """Cuts, joins and overlays `segments` into `output_path` with a single
    encode. Skips the work when `output_path` already exists."""
    if output_path.exists():
        logger.info(f"Processed video already exists, skipping: {output_path}")
        return str(output_path)
    if not segments:
        raise ValueError("A match needs at least one segment")

    infos = {}
    for name in {seg.source for seg in segments}:
        try:
            infos[name] = media_probe.probe(source_dir / name)
        except (OSError, ValueError, subprocess.CalledProcessError) as e:
            raise RuntimeError(f"Cannot read source {name}: {e}") from e

    inputs = [
        RenderInput(
            str(source_dir / seg.source),
            seg.start,
            seg.end,
            infos[seg.source].has_audio,
            infos[seg.source].width,
            infos[seg.source].height,
            infos[seg.source].fps or DEFAULT_FPS,
        )
        for seg in segments
    ]
    width, height = inputs[0].width, inputs[0].height
    fps = infos[segments[0].source].fps
    total_duration = sum(inp.duration for inp in inputs)
    show_thanks, thanks_start = overlay_timing(total_duration)

    logo_path = str(config.LOGO_PATH) if config.LOGO_PATH.exists() else None
    logo_size = int(width * 0.1) if logo_path else None
    if not logo_path:
        logger.warning(f"Logo not found at {config.LOGO_PATH}, skipping watermark")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # A partial left by an earlier process (killed, or an orphaned ffmpeg
    # still writing to it) is never reused: this process writes its own.
    for stale in output_path.parent.glob(f"{output_path.name}*.partial"):
        stale.unlink(missing_ok=True)
    partial = output_path.with_name(f"{output_path.name}.{os.getpid()}.partial")

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cafe_pngs = []
            for i, word in enumerate(render_cafe_game_words(width, height)):
                cafe_pngs.append(str(Path(tmp_dir) / f"intro_word{i}.png"))
                word.save(cafe_pngs[-1])
            thanks_png = None
            if show_thanks:
                thanks_png = str(Path(tmp_dir) / "thanks_overlay.png")
                render_thanks_overlay(width, height).save(thanks_png)
            badge_png, badge_width = None, None
            if logo_path and logo_size:
                try:
                    badge = render_logo_badge(logo_path, logo_size)
                except OSError as e:  # includes PIL.UnidentifiedImageError
                    raise RuntimeError(f"Cannot read logo {logo_path}: {e}") from e
                badge_png = str(Path(tmp_dir) / "logo_badge.png")
                badge_width = badge.width
                badge.save(badge_png)

            for use_hardware in (True, False):
                cmd = build_render_command(
                    inputs,
                    cafe_pngs,
                    thanks_png,
                    thanks_start,
                    badge_png,
                    badge_width,
                    str(partial),
                    use_hardware,
                    fps=fps,
                )
                returncode, stderr = _run_ffmpeg(cmd, total_duration, progress)
                if returncode == 0:
                    break
                if use_hardware:
                    logger.warning("Hardware encoder failed, retrying with libx264...")
            else:
                tail = "\n".join(stderr.strip().splitlines()[-STDERR_TAIL_LINES:])
                raise RuntimeError(f"FFmpeg failed with code {returncode}:\n{tail}")

        partial.replace(output_path)
    finally:
        partial.unlink(missing_ok=True)

    if progress:
        progress(100.0)
    logger.info(f"Match rendered: {output_path}")
    return str(output_path)
