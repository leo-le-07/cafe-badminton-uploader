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


def build_render_command(
    inputs: list[RenderInput],
    cafe_png: str,
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
    encoder_args = ["-c:v", "h264_videotoolbox"] if use_hardware else ["-c:v", "libx264", "-preset", "ultrafast"]
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
            chains.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={inp.duration:.6f},{_AUDIO_FORMAT}[a{i}]")
        concat_pads += f"[v{i}][a{i}]"
    chains.append(f"{concat_pads}concat=n={len(inputs)}:v=1:a=1[cat][aout]")

    idx = len(inputs)
    args += ["-i", cafe_png]
    chains.append(f"[cat][{idx}:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='lte(t,{OVERLAY_DURATION})'[ov1]")
    last = "ov1"
    if thanks_png:
        idx += 1
        args += ["-i", thanks_png]
        chains.append(f"[{last}][{idx}:v]overlay=x=(W-w)/2:y=(H-h)/2:enable='gte(t,{thanks_start:.3f})'[ov2]")
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


def _run_ffmpeg(cmd: list[str], total_duration: float, progress: Callable[[float], None] | None) -> tuple[int, str]:
    """Runs ffmpeg, reporting percent done from `-progress` output. Returns
    (returncode, stderr)."""
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=err, stdin=subprocess.DEVNULL, text=True)
        assert proc.stdout is not None
        try:
            with proc.stdout:
                for line in proc.stdout:
                    key, _, value = line.strip().partition("=")
                    if key == "out_time_us" and progress and value.lstrip("-").isdigit() and total_duration > 0:
                        progress(max(0.0, min(100.0, int(value) / 1e6 / total_duration * 100)))
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
            str(source_dir / seg.source), seg.start, seg.end,
            infos[seg.source].has_audio, infos[seg.source].width, infos[seg.source].height,
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
            cafe_png = str(Path(tmp_dir) / "cafe_overlay.png")
            render_cafe_game_overlay(width, height).save(cafe_png)
            thanks_png = None
            if show_thanks:
                thanks_png = str(Path(tmp_dir) / "thanks_overlay.png")
                render_thanks_overlay(width, height).save(thanks_png)

            for use_hardware in (True, False):
                cmd = build_render_command(
                    inputs, cafe_png, thanks_png, thanks_start, logo_path, logo_size,
                    str(partial), use_hardware, fps=fps,
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
