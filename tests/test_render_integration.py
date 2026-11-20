import json
import shutil
import subprocess
from pathlib import Path

import pytest

import config
import video_overlay
from app.models import Segment
from video_overlay import render_match

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None, reason="ffmpeg not installed"
)


def _make_source(path: Path, seconds: float, audio: bool = True) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=320x240:rate=30:duration={seconds}",
    ]
    if audio:
        cmd += ["-f", "lavfi", "-i", f"sine=duration={seconds}"]
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac"]
    cmd.append(str(path))
    subprocess.run(cmd, check=True, capture_output=True)


@pytest.fixture(scope="module")
def sources(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("sources")
    _make_source(d / "a.mov", 6)
    _make_source(d / "b.mov", 6)
    _make_source(d / "silent.mov", 6, audio=False)
    return d


def _streams(path: Path) -> tuple[float, set[str]]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        capture_output=True,
        check=True,
    )
    data = json.loads(out.stdout)
    return float(data["format"]["duration"]), {s["codec_type"] for s in data["streams"]}


# Each frame of an indexed source shows its own number N: the left half has
# the grey level 16 + (N // 16) * 13, the right half 16 + (N % 16) * 13. The
# levels are far enough apart to read back after a lossy encode.
_SIZE = (320, 240)
_SAMPLE = (32, 24)


def _make_indexed_source(path: Path, rate: str, frames: int) -> None:
    geq = "geq=lum='if(lt(X,W/2),16+floor(N/16)*13,16+mod(N,16)*13)':cb=128:cr=128"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=black:s={_SIZE[0]}x{_SIZE[1]}:r={rate}",
            "-f",
            "lavfi",
            "-i",
            "sine=sample_rate=48000",
            "-vf",
            f"format=yuv420p,{geq}",
            "-frames:v",
            str(frames),
            "-c:v",
            "libx264",
            "-g",
            "30",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _frame_numbers(path: Path) -> list[int]:
    """The source frame number shown in each frame of `path`, read from the
    bottom rows (clear of the CAFE GAME overlay and the logo)."""
    w, h = _SAMPLE
    raw = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-i",
            str(path),
            "-vf",
            f"scale={w}:{h}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "yuv420p",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    luma, stride = w * h, w * h * 3 // 2
    numbers = []
    for offset in range(0, len(raw) - stride + 1, stride):
        frame = raw[offset : offset + luma]

        def level(x0: int, x1: int) -> int:
            values = [frame[r * w + c] for r in range(h - 3, h) for c in range(x0, x1)]
            return round((sum(values) / len(values) - 16) / 13)

        numbers.append(level(2, 6) * 16 + level(w - 6, w - 2))
    return numbers


@pytest.fixture(scope="module")
def indexed(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("indexed")
    _make_indexed_source(d / "f30.mov", "30", 120)
    _make_indexed_source(d / "f2997.mov", "30000/1001", 120)
    assert _frame_numbers(d / "f30.mov") == list(range(120))
    return d


@pytest.mark.parametrize(
    "name, fps",
    [("f30.mov", 30.0), ("f2997.mov", 30000 / 1001)],
)
@pytest.mark.parametrize("first, stop", [(0, 10), (1, 11), (2, 12), (7, 37), (44, 54)])
def test_cut_keeps_exactly_the_marked_frames(indexed, tmp_path, name, fps, first, stop):
    """A segment [first/fps, stop/fps) keeps frames first..stop-1: the frame
    under the playhead at I is kept, the one at O is dropped."""
    out = tmp_path / "processed.mov"
    render_match([Segment(name, first / fps, stop / fps)], indexed, out)
    assert _frame_numbers(out) == list(range(first, stop))


def test_join_of_two_frame_rates_keeps_exact_frames(indexed, tmp_path):
    out = tmp_path / "processed.mov"
    ntsc = 30000 / 1001
    render_match(
        [Segment("f30.mov", 3 / 30, 8 / 30), Segment("f2997.mov", 5 / ntsc, 9 / ntsc)],
        indexed,
        out,
    )
    assert _frame_numbers(out) == [3, 4, 5, 6, 7, 5, 6, 7, 8]


def test_segment_ending_at_end_of_file_keeps_last_frame(indexed, tmp_path):
    out = tmp_path / "processed.mov"
    info_duration = 120 / 30
    render_match([Segment("f30.mov", 100 / 30, info_duration)], indexed, out)
    assert _frame_numbers(out) == list(range(100, 120))


def _listing(d: Path) -> dict[str, float]:
    return {p.name: p.stat().st_mtime for p in d.iterdir()}


def test_two_segments_one_file(sources, tmp_path):
    before = _listing(sources)
    out = tmp_path / "processed.mov"
    result = render_match(
        [Segment("a.mov", 1, 3), Segment("a.mov", 4, 5)], sources, out
    )
    assert result == str(out)
    duration, kinds = _streams(out)
    assert duration == pytest.approx(3.0, abs=0.1)
    assert kinds == {"video", "audio"}
    assert _listing(sources) == before
    assert list(tmp_path.iterdir()) == [out]


def test_segments_across_two_files(sources, tmp_path):
    out = tmp_path / "processed.mov"
    render_match([Segment("a.mov", 4, 6), Segment("b.mov", 0, 1.5)], sources, out)
    duration, _ = _streams(out)
    assert duration == pytest.approx(3.5, abs=0.1)


def test_source_without_audio(sources, tmp_path):
    out = tmp_path / "processed.mov"
    render_match([Segment("silent.mov", 0, 2), Segment("a.mov", 0, 2)], sources, out)
    duration, kinds = _streams(out)
    assert duration == pytest.approx(4.0, abs=0.1)
    assert "audio" in kinds


def test_progress_reaches_100(sources, tmp_path):
    values: list[float] = []
    render_match(
        [Segment("a.mov", 0, 2)],
        sources,
        tmp_path / "processed.mov",
        progress=values.append,
    )
    assert values
    assert values[-1] >= 99
    assert all(0 <= v <= 100 for v in values)


def test_existing_output_is_not_rerendered(sources, tmp_path):
    out = tmp_path / "processed.mov"
    out.write_bytes(b"already rendered")
    result = render_match([Segment("a.mov", 0, 2)], sources, out)
    assert result == str(out)
    assert out.read_bytes() == b"already rendered"


def test_failed_render_leaves_no_output_file(sources, tmp_path):
    out = tmp_path / "processed.mov"
    with pytest.raises(RuntimeError):
        render_match([Segment("missing.mov", 0, 2)], sources, out)
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []


def test_ffmpeg_failure_leaves_no_partial_file(sources, tmp_path, monkeypatch):
    bad_logo = tmp_path / "logo.png"
    bad_logo.write_bytes(b"not a png")
    monkeypatch.setattr(config, "LOGO_PATH", bad_logo)
    out_dir = tmp_path / "ws"
    out = out_dir / "processed.mov"
    with pytest.raises(RuntimeError, match="FFmpeg failed"):
        render_match([Segment("a.mov", 0, 2)], sources, out)
    assert list(out_dir.iterdir()) == []


def test_hardware_failure_falls_back_to_libx264(sources, tmp_path, monkeypatch):
    real_run = video_overlay._run_ffmpeg
    encoders: list[str] = []

    def hardware_fails(cmd, total_duration, progress):
        encoders.append(cmd[cmd.index("-c:v") + 1])
        if cmd[cmd.index("-c:v") + 1] == "h264_videotoolbox":
            return 1, "hardware encoder unavailable"
        return real_run(cmd, total_duration, progress)

    monkeypatch.setattr(video_overlay, "_run_ffmpeg", hardware_fails)
    out = tmp_path / "processed.mov"
    render_match([Segment("a.mov", 0, 2)], sources, out)
    assert encoders == ["h264_videotoolbox", "libx264"]
    duration, _ = _streams(out)
    assert duration == pytest.approx(2.0, abs=0.1)


def test_rotated_source_renders_upright(sources, tmp_path):
    rotated = tmp_path / "src" / "rotated.mov"
    rotated.parent.mkdir()
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-display_rotation",
            "90",
            "-i",
            str(sources / "a.mov"),
            "-c",
            "copy",
            str(rotated),
        ],
        check=True,
        capture_output=True,
    )
    probed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "v:0",
            str(rotated),
        ],
        capture_output=True,
        check=True,
    )
    side_data = json.loads(probed.stdout)["streams"][0].get("side_data_list", [])
    assert any(abs(sd.get("rotation", 0)) == 90 for sd in side_data), (
        "rotation metadata was not written"
    )

    out = tmp_path / "processed.mov"
    render_match([Segment("rotated.mov", 0, 2)], rotated.parent, out)

    probed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            "-select_streams",
            "v:0",
            str(out),
        ],
        capture_output=True,
        check=True,
    )
    stream = json.loads(probed.stdout)["streams"][0]
    assert (stream["width"], stream["height"]) == (240, 320)


def test_aborting_progress_kills_ffmpeg(sources, tmp_path, monkeypatch):
    children: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        children.append(proc)
        return proc

    monkeypatch.setattr(video_overlay.subprocess, "Popen", recording_popen)

    class Cancelled(Exception):
        pass

    def cancel(_value: float) -> None:
        raise Cancelled

    out = tmp_path / "processed.mov"
    with pytest.raises(Cancelled):
        render_match([Segment("a.mov", 0, 4)], sources, out, progress=cancel)

    ffmpeg = [p for p in children if p.args[0] == "ffmpeg"]
    assert len(ffmpeg) == 1
    assert ffmpeg[0].poll() is not None
    assert not out.exists()
    assert list(tmp_path.iterdir()) == []
