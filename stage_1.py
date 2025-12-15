from collections.abc import Iterator
from pathlib import Path
from datetime import datetime

import config
import json
import cv2
import numpy as np

MATCH_TYPES = {
    "ms": "Men's Singles",
    "md": "Men's Doubles",
    "ws": "Women's Singles",
    "wd": "Women's Doubles",
    "xd": "Mixed Doubles",
}

FIXED_TAGS = "#sunbadminton #badminton #cafebadminton"


def scan_videos(input_path: Path) -> Iterator[Path]:
    return (
        video
        for video in input_path.iterdir()
        if video.is_file() and video.suffix in {".mov", ".MOV"}
    )


def parse_filename(filename: str) -> dict[str, str]:
    filepath = Path(filename)
    name = filepath.stem
    parts = name.split("_")

    if len(parts) < 2:
        raise ValueError(f"Invalid filename format: {filename}")

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

    metadata = {
        "match_type": match_type,
        "team1": team1,
        "team2": team2,
        "tournament": tournament,
    }

    return metadata


def format_team_names(team1: list[str], team2: list[str], separator: str = "/") -> str:
    team1_str = separator.join(team1)
    team2_str = separator.join(team2)
    return f"{team1_str} vs {team2_str}"


def create_title(metadata: dict) -> str:
    title = ""

    current_date = datetime.now().strftime("%d %b %Y")
    teams = format_team_names(metadata["team1"], metadata["team2"])

    parts = [
        teams,
        f"{metadata['tournament']} ({current_date})",
    ]

    title = " | ".join(parts)

    return title


def create_tag(name: str) -> str:
    tag = name.lower()
    tag = tag.replace("men's", "mens").replace("women's", "womens")
    tag = tag.replace("'s", "").replace("'", "")
    tag = tag.replace(" ", "")
    tag = "".join(c for c in tag if c.isalnum())

    return tag


def create_description(metadata: dict) -> str:
    description = ""
    current_date = datetime.now().strftime("%d %b %Y")
    teams = format_team_names(metadata["team1"], metadata["team2"])
    dynamic_tags = [
        f"#{create_tag(metadata['match_type'])}",
        f"#{create_tag(metadata['tournament'])}",
    ]

    all_tags = f"{FIXED_TAGS} {' '.join(dynamic_tags)}"
    parts = [
        all_tags,
        "",  # Extra newline after tags
        f"{metadata['tournament']} ({current_date})",
        metadata["match_type"],
        teams,
    ]

    description = "\n".join(parts)
    return description


def create_metadata_for_video(video_path: Path):
    metadata = parse_filename(video_path.name)
    metadata["title"] = create_title(metadata)
    metadata["description"] = create_description(metadata)

    output_dir = config.INPUT_DIR / video_path.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(output_dir / "metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=4)


def create_frame_candidates(video_path: Path):
    cap = cv2.VideoCapture(str(video_path.resolve()))

    if not cap.isOpened():
        raise IOError(f"Error opening video file: {video_path}")

    try:
        output_dir = config.INPUT_DIR / video_path.stem / "candidates"
        output_dir.mkdir(parents=True, exist_ok=True)

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            raise ValueError(f"Video file has zero frames: {video_path}")

        frame_indices = np.linspace(
            0, total_frames - 1, config.CANDIDATE_THUMBNAIL_NUM, dtype=int
        )

        for i, frame_idx in enumerate(frame_indices):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()

            if not ret:
                print(f"Warning: Could not read frame {frame_idx} from {video_path}")
                continue

            file_name = f"frame_{frame_idx}.jpg"
            out_path = output_dir / file_name

            cv2.imwrite(str(out_path), frame)

    finally:
        cap.release()


if __name__ == "__main__":
    videos = scan_videos(config.INPUT_DIR)

    for video in videos:
        create_metadata_for_video(video)
        create_frame_candidates(video)
