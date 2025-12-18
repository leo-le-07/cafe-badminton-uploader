from schemas import MatchMetadata
from pathlib import Path
from datetime import datetime

import config
import json
import cv2
import numpy as np
import constants
import utils

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


def calculate_frame_indices(total_frames: int, num_candidates: int) -> np.ndarray:
    if total_frames < 0:
        raise ValueError("Video must have at least one frame")
    return np.linspace(0, total_frames - 1, num_candidates, dtype=int)


def create_metadata(video_path: Path) -> MatchMetadata:
    video_stem = video_path.stem
    current_date = datetime.now().strftime("%Y-%m-%d")

    tournament, match_type, team1, team2 = parse_filename(video_stem)
    title = create_title(tournament, team1, team2, current_date)
    description = create_description(tournament, match_type, team1, team2, current_date)

    metadata: MatchMetadata = {
        "matchType": match_type,
        "team1Names": team1,
        "team2Names": team2,
        "tournament": tournament,
        "title": title,
        "description": description,
        "category": constants.CATEGORY_SPORTS,
        "privacyStatus": config.VIDEO_PRIVACY_STATUS,
    }

    return metadata


def store(video_path, metadata: MatchMetadata) -> None:
    metadata_path = utils.get_metadata_path(video_path)

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)


def create_frame_candidates(
    video_path: Path, output_dir: Path, num_candidates: int
) -> None:
    cap = cv2.VideoCapture(str(video_path.resolve()))

    if not cap.isOpened():
        raise IOError(f"Error opening video file: {video_path}")

    try:
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        frame_indices = calculate_frame_indices(total_frames, num_candidates)

        output_dir.mkdir(parents=True, exist_ok=True)

        for i, frame_idx in enumerate(frame_indices):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()

            if not ret:
                print(f"Warning: Could not read frame {frame_idx} from {video_path}")
                continue

            out_path = output_dir / f"frame_{frame_idx}.jpg"
            cv2.imwrite(str(out_path), frame)

    finally:
        cap.release()


def run():
    videos = utils.scan_videos(config.INPUT_DIR)

    for video_path in videos:
        workspace_dir = utils.get_workspace_dir(video_path)
        workspace_dir.mkdir(parents=True, exist_ok=True)

        try:
            metadata = create_metadata(video_path)
            store(video_path, metadata)
        except ValueError as e:
            print(f"Skipping {video_path.name}: {e}")
            continue

        candidate_dir = utils.get_candidate_dir(video_path)
        create_frame_candidates(
            video_path, candidate_dir, config.CANDIDATE_THUMBNAIL_NUM
        )


if __name__ == "__main__":
    run()
