from collections.abc import Iterator
from pathlib import Path

import config

MATCH_TYPES = {
    "ms": "Men's Singles",
    "md": "Men's Doubles",
    "ws": "Women's Singles",
    "wd": "Women's Doubles",
    "xd": "Mixed Doubles",
}


def scan_videos(input_path: Path, extension: str = ".mov") -> Iterator[Path]:
    videos = input_path.glob(f"*{extension}")

    return videos


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


if __name__ == "__main__":
    scan_videos(config.INPUT_DIR)
