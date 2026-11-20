import json
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class SourceInfo:
    name: str
    duration: float
    fps: float
    width: int
    height: int
    has_audio: bool
    recorded_at: str  # ISO 8601, local time

    def to_dict(self) -> dict:
        return asdict(self)


_cache: dict[tuple[str, int, float], SourceInfo] = {}


def _parse_rate(rate: str) -> float:
    num, _, den = rate.partition("/")
    if not den:
        return float(num)
    if float(den) == 0:
        return 0.0
    return float(num) / float(den)


def _fps(video: dict) -> float:
    """Average frame rate; `r_frame_rate` can be a timebase-like value on
    variable-frame-rate phone recordings, so it is only a fallback."""
    for field in ("avg_frame_rate", "r_frame_rate"):
        try:
            rate = _parse_rate(video.get(field, "0/0"))
        except ValueError:
            continue
        if rate > 0:
            return rate
    return 0.0


def _rotation(video: dict) -> int:
    for side_data in video.get("side_data_list", []):
        if "rotation" in side_data:
            return int(float(side_data["rotation"]))
    try:
        return int(float(video.get("tags", {}).get("rotate", 0)))
    except ValueError:
        return 0


def _display_size(video: dict) -> tuple[int, int]:
    """Width and height as shown, after the rotation that ffmpeg applies."""
    width, height = int(video["width"]), int(video["height"])
    if _rotation(video) % 180 == 90:
        return height, width
    return width, height


def _recorded_at(fmt: dict, mtime: float) -> str:
    creation_time = fmt.get("tags", {}).get("creation_time")
    if creation_time:
        try:
            return datetime.fromisoformat(creation_time).astimezone().isoformat()
        except ValueError:
            pass
    return datetime.fromtimestamp(mtime).astimezone().isoformat()


def probe(path: Path) -> SourceInfo:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime)
    if key in _cache:
        return _cache[key]

    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    fmt = data.get("format", {})
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"No video stream in {path}")

    width, height = _display_size(video)
    info = SourceInfo(
        name=path.name,
        duration=float(fmt["duration"]),
        fps=_fps(video),
        width=width,
        height=height,
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        recorded_at=_recorded_at(fmt, stat.st_mtime),
    )
    _cache[key] = info
    return info


def playback_path(path: Path) -> Path:
    """Path the browser should play for a source. No proxy is made: browsers
    play the recordings directly."""
    return path
