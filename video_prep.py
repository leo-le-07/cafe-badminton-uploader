from custom_exceptions import CreateMetadataError
from schemas import MatchMetadata
from pathlib import Path
from datetime import datetime
from dataclasses import asdict

import config
import json
import subprocess
import cv2
import numpy as np
import constants
import utils
from logger import get_logger

logger = get_logger(__name__)

MATCH_TYPES = {
    "ms": "Men's Singles",
    "md": "Men's Doubles",
    "ws": "Women's Singles",
    "wd": "Women's Doubles",
    "xd": "Mixed Doubles",
}

FIXED_TAGS = "#sunbadminton #badminton #cafebadminton"


def parse_filename(video_stem: str) -> tuple[str, str, list[str], list[str]]:
    parts = video_stem.split("_")

    if len(parts) < 2:
        raise ValueError(f"Invalid filename format: {video_stem}")

    match_type_acronym = parts[0].lower()
    if match_type_acronym not in MATCH_TYPES:
        raise ValueError(f"Invalid match type acronym: {match_type_acronym}")
    match_type = MATCH_TYPES[match_type_acronym]

    teams = parts[1].split("vs")
    if len(teams) != 2:
        raise ValueError(f"Invalid teams format: {parts[1]}")
    team1 = teams[0].split("z")
    team2 = teams[1].split("z")

    tournament = (parts[2] if len(parts) > 2 else "cafe game").title()

    return tournament, match_type, team1, team2


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

    all_tags = f"{FIXED_TAGS} {' '.join(dynamic_tags)}"
    parts = [
        all_tags,
        "",
        f"{tournament} ({match_date_str})",
        match_type,
        teams,
    ]

    description = "\n".join(parts)
    return description


def create_metadata(video_path: Path) -> MatchMetadata:
    video_stem = video_path.stem
    current_date = datetime.now().strftime("%Y-%m-%d")

    tournament, match_type, team1, team2 = parse_filename(video_stem)
    title = create_title(tournament, team1, team2, current_date)
    description = create_description(tournament, match_type, team1, team2, current_date)

    metadata = MatchMetadata(
        match_type=match_type,
        team1_names=team1,
        team2_names=team2,
        tournament=tournament,
        title=title,
        description=description,
        category=constants.CATEGORY_SPORTS,
    )

    return metadata


def store(video_path, metadata: MatchMetadata) -> None:
    metadata_path = utils.get_metadata_path(video_path)

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(asdict(metadata), f, ensure_ascii=False, indent=4)


def create_workspace(video_path: Path) -> None:
    workspace_dir = utils.get_workspace_dir(video_path)
    workspace_dir.mkdir(parents=True, exist_ok=True)


def create_and_store_metadata(video_path: str) -> MatchMetadata:
    path = Path(video_path)
    create_workspace(path)
    try:
        metadata = create_metadata(path)
        store(path, metadata)

        return metadata
    except ValueError as e:
        raise CreateMetadataError(e)


def score_frame(frame: np.ndarray, prev_frame: np.ndarray | None = None) -> dict:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())

    mean_brightness = float(np.mean(gray))
    brightness = max(0.0, 1.0 - abs(mean_brightness - 128.0) / 128.0)

    if prev_frame is not None:
        prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
        motion = float(np.mean(np.abs(gray.astype(np.float32) - prev_gray.astype(np.float32))))
    else:
        motion = 0.0

    return {"sharpness": sharpness, "brightness": brightness, "motion": motion}


def _get_video_duration_seconds(video_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            video_path,
        ],
        capture_output=True,
        check=True,
    )
    info = json.loads(result.stdout)
    return float(info["format"]["duration"])


def _extract_frame_at(video_path: str, timestamp: float) -> np.ndarray | None:
    result = subprocess.run(
        [
            "ffmpeg",
            "-ss", f"{timestamp:.3f}",
            "-i", video_path,
            "-vframes", "1",
            "-f", "image2",
            "-vcodec", "mjpeg",
            "-q:v", "2",
            "-loglevel", "error",
            "pipe:1",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    buf = np.frombuffer(result.stdout, dtype=np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def auto_select_thumbnail(video_path: str) -> None:
    path = Path(video_path)

    output_path = utils.get_selected_candidate_path(path)
    if output_path.exists():
        logger.info(f"Thumbnail already selected, skipping: {output_path}")
        return

    num_candidates = config.CANDIDATE_THUMBNAIL_NUM

    duration = _get_video_duration_seconds(video_path)
    start = duration * 0.1
    end = duration * 0.9
    timestamps = np.linspace(start, end, num_candidates)

    frames = []
    raw_scores = []
    prev_frame = None

    for timestamp in timestamps:
        frame = _extract_frame_at(video_path, timestamp)
        if frame is None:
            logger.warning(f"Could not extract frame at {timestamp:.2f}s from {path}")
            continue
        raw_scores.append(score_frame(frame, prev_frame))
        frames.append(frame)
        prev_frame = frame

    if not frames:
        raise ValueError(f"Could not extract any frames from {path}")

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
