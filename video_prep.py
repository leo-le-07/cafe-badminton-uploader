from schemas import MatchMetadata
from pathlib import Path
from dataclasses import asdict

from app.models import Segment

import config
import json
import subprocess
import cv2
import numpy as np
import constants
import utils
from logger import get_logger

logger = get_logger(__name__)


def _format_team_names(team1: list[str], team2: list[str], separator: str = "/") -> str:
    team1_str = separator.join(team1)
    team2_str = separator.join(team2)
    return f"{team1_str} vs {team2_str}"


def create_title(
    tournament: str, team1: list[str], team2: list[str], match_date_str: str
) -> str:
    title = ""

    teams = _format_team_names(team1, team2)

    parts = [
        teams,
        f"{tournament} ({match_date_str})",
    ]

    title = " | ".join(parts)

    return title


def _create_tag(name: str) -> str:
    tag = name.lower()
    tag = tag.replace("men's", "mens").replace("women's", "womens")
    tag = tag.replace("'s", "").replace("'", "")
    tag = tag.replace(" ", "")
    tag = "".join(c for c in tag if c.isalnum())

    return tag


def create_description(
    tournament: str,
    match_type: str,
    team1: list[str],
    team2: list[str],
    match_date_str: str,
) -> str:
    description = ""
    teams = _format_team_names(team1, team2)
    dynamic_tags = [
        f"#{_create_tag(match_type)}",
        f"#{_create_tag(tournament)}",
    ]

    all_tags = f"{constants.FIXED_TAGS} {' '.join(dynamic_tags)}"
    parts = [
        all_tags,
        "",
        f"{tournament} ({match_date_str})",
        match_type,
        teams,
    ]

    description = "\n".join(parts)
    return description


def create_metadata_from_fields(
    match_type: str,
    team1: list[str],
    team2: list[str],
    tournament: str,
    match_date: str,
    theme: str | None = None,
) -> MatchMetadata:
    if match_type not in constants.MATCH_TYPES:
        raise ValueError(f"Invalid match type: {match_type}")
    match_type_name = constants.MATCH_TYPES[match_type]

    title = create_title(tournament, team1, team2, match_date)
    description = create_description(
        tournament, match_type_name, team1, team2, match_date
    )

    return MatchMetadata(
        match_type=match_type_name,
        team1_names=team1,
        team2_names=team2,
        tournament=tournament,
        title=title,
        description=description,
        category=constants.CATEGORY_SPORTS,
        theme=theme,
    )


def store(video_path, metadata: MatchMetadata) -> None:
    metadata_path = utils.get_metadata_path(video_path)

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(asdict(metadata), f, ensure_ascii=False, indent=4)


def score_frame(frame: np.ndarray, prev_frame: np.ndarray | None = None) -> dict:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    mean_brightness = float(np.mean(gray))
    brightness = max(0.0, 1.0 - abs(mean_brightness - 128.0) / 128.0)

    if prev_frame is not None:
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        motion = float(
            np.mean(np.abs(gray.astype(np.float32) - prev_gray.astype(np.float32)))
        )
    else:
        motion = 0.0

    return {"sharpness": sharpness, "brightness": brightness, "motion": motion}


def _extract_frame_at(video_path: str, timestamp: float) -> np.ndarray | None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-ss",
            f"{timestamp:.3f}",
            "-i",
            video_path,
            "-vframes",
            "1",
            "-f",
            "image2",
            "-vcodec",
            "mjpeg",
            "-q:v",
            "2",
            "-loglevel",
            "error",
            "pipe:1",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    buf = np.frombuffer(result.stdout, dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def sample_timestamps(segments: list[Segment], count: int) -> list[tuple[str, float]]:
    """Spread `count` points evenly over the kept footage of a match, skipping
    its first and last 10%, and map each back to (source, time in source)."""
    total = sum(seg.end - seg.start for seg in segments)
    if count <= 0 or total <= 0:
        return []

    points = []
    for offset in np.linspace(total * 0.1, total * 0.9, count):
        elapsed = 0.0
        for seg in segments:
            length = seg.end - seg.start
            if offset <= elapsed + length or seg is segments[-1]:
                points.append(
                    (seg.source, float(seg.start + min(offset - elapsed, length)))
                )
                break
            elapsed += length
    return points


def select_thumbnail_from_segments(
    segments: list[Segment], source_dir: Path, output_path: Path
) -> None:
    if output_path.exists():
        logger.info(f"Thumbnail already selected, skipping: {output_path}")
        return

    frames = []
    raw_scores = []
    prev_frame = None

    for source, timestamp in sample_timestamps(
        segments, config.CANDIDATE_THUMBNAIL_NUM
    ):
        frame = _extract_frame_at(str(source_dir / source), timestamp)
        if frame is None:
            logger.warning(f"Could not extract frame at {timestamp:.2f}s from {source}")
            continue
        raw_scores.append(score_frame(frame, prev_frame))
        frames.append(frame)
        prev_frame = frame

    if not frames:
        raise ValueError(
            f"Could not extract any frames from {len(segments)} segment(s)"
        )

    sharpness_values = [s["sharpness"] for s in raw_scores]
    motion_values = [s["motion"] for s in raw_scores]
    max_sharpness = max(sharpness_values) or 1.0
    max_motion = max(motion_values) or 1.0

    composite_scores = [
        0.4 * (s["sharpness"] / max_sharpness)
        + 0.3 * s["brightness"]
        + 0.3 * (s["motion"] / max_motion)
        for s in raw_scores
    ]

    best_frame = frames[int(np.argmax(composite_scores))]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), best_frame)
    logger.info(f"Auto-selected thumbnail saved to {output_path}")
