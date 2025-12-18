import pytest
from pathlib import Path
from unittest.mock import patch
import numpy as np

from video_prep import (
    create_title,
    _format_team_names,
    parse_filename,
    _create_tag,
    create_description,
    calculate_frame_indices,
    create_metadata,
)


@pytest.mark.parametrize(
    "filename, expected",
    [
        (
            "ms_LeovsKhanh",
            ("Cafe Game", "Men's Singles", ["Leo"], ["Khanh"]),
        ),
        (
            "ws_AnhvsMai",
            ("Cafe Game", "Women's Singles", ["Anh"], ["Mai"]),
        ),
        (
            "md_DenzTuvsHuyzHa",
            ("Cafe Game", "Men's Doubles", ["Den", "Tu"], ["Huy", "Ha"]),
        ),
        (
            "wd_AnhzMaivsLinhzHoa",
            ("Cafe Game", "Women's Doubles", ["Anh", "Mai"], ["Linh", "Hoa"]),
        ),
        (
            "xd_DenzAnhvsHuyzMai_Sunbad Tour Game",
            ("Sunbad Tour Game", "Mixed Doubles", ["Den", "Anh"], ["Huy", "Mai"]),
        ),
        (
            "ms_LeovsKhanh_Summer Cup 2024",
            ("Summer Cup 2024", "Men's Singles", ["Leo"], ["Khanh"]),
        ),
    ],
)
def test_parse_filename_valid(filename, expected):
    result = parse_filename(filename)
    assert result == expected


@pytest.mark.parametrize(
    "filename, error_match",
    [
        ("LeovsKhanh", "Invalid filename format"),
        ("invalid_LeovsKhanh", "Invalid match type"),
        ("ms_LeoKhanh", "Invalid teams format"),
        ("ms_Leo_vs_Khanh_vs_Extra", "Invalid teams format"),
    ],
)
def test_parse_filename_invalid(filename, error_match):
    with pytest.raises(ValueError, match=error_match):
        parse_filename(filename)


@pytest.mark.parametrize(
    "team1, team2, separator, expected",
    [
        (["Leo"], ["Khanh"], "/", "Leo vs Khanh"),
        (["Den", "Tu"], ["Huy", "Ha"], None, "Den/Tu vs Huy/Ha"),
        (["Den", "Tu"], ["Huy", "Ha"], " & ", "Den & Tu vs Huy & Ha"),
        (["Leo"], ["Huy", "Ha"], "/", "Leo vs Huy/Ha"),
    ],
)
def test_format_team_names(team1, team2, separator, expected):
    if separator:
        result = _format_team_names(team1, team2, separator)
    else:
        result = _format_team_names(team1, team2)
    assert result == expected


@pytest.mark.parametrize(
    "tournament, team1, team2, match_date_str, expected",
    [
        (
            "Winter League",
            ["Anh"],
            ["Linh"],
            "01 Jan 2023",
            "Anh vs Linh | Winter League (01 Jan 2023)",
        ),
        (
            "Cafe Game",
            ["Den", "Tu"],
            ["Huy", "Ha"],
            "15 Dec 2024",
            "Den/Tu vs Huy/Ha | Cafe Game (15 Dec 2024)",
        ),
        (
            "Summer Cup",
            ["Leo"],
            ["Khanh"],
            "20 Jul 2024",
            "Leo vs Khanh | Summer Cup (20 Jul 2024)",
        ),
    ],
)
def test_create_title(tournament, team1, team2, match_date_str, expected):
    result = create_title(tournament, team1, team2, match_date_str)
    assert result == expected


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Men's Singles", "menssingles"),
        ("Women's Doubles", "womensdoubles"),
        ("Mixed Doubles", "mixeddoubles"),
        ("Summer Cup 2024", "summercup2024"),
        ("Cafe Game", "cafegame"),
        ("Sunbad Tour Game", "sunbadtourgame"),
    ],
)
def test_create_tag(name, expected):
    result = _create_tag(name)
    assert result == expected


@pytest.mark.parametrize(
    "tournament, match_type, team1, team2, match_date_str",
    [
        ("Cafe Game", "Men's Singles", ["Leo"], ["Khanh"], "2024-12-15"),
        ("Winter League", "Men's Doubles", ["Den", "Tu"], ["Huy", "Ha"], "2024-01-20"),
    ],
)
def test_create_description(tournament, match_type, team1, team2, match_date_str):
    result = create_description(tournament, match_type, team1, team2, match_date_str)

    assert "#sunbadminton" in result
    assert "#badminton" in result
    assert "#cafebadminton" in result
    assert f"#{_create_tag(match_type)}" in result
    assert f"#{_create_tag(tournament)}" in result
    assert f"{tournament} ({match_date_str})" in result
    assert match_type in result
    assert "vs" in result


@pytest.mark.parametrize(
    "total_frames, num_candidates, expected",
    [
        (100, 5, [0, 24, 49, 74, 99]),
        (1000, 10, [0, 111, 222, 333, 444, 555, 666, 777, 888, 999]),
        (50, 3, [0, 24, 49]),
        (10, 2, [0, 9]),
    ],
)
def test_calculate_frame_indices(total_frames, num_candidates, expected):
    result = calculate_frame_indices(total_frames, num_candidates)
    assert isinstance(result, np.ndarray)
    assert list(result) == expected


def test_calculate_frame_indices_invalid():
    with pytest.raises(ValueError, match="at least one frame"):
        calculate_frame_indices(-1, 5)


@patch("video_prep.datetime")
def test_create_metadata(mock_datetime):
    mock_datetime.now.return_value.strftime.return_value = "2024-12-15"
    video_path = Path("ms_LeovsKhanh_Summer Cup.mov")

    result = create_metadata(video_path)

    assert result["matchType"] == "Men's Singles"
    assert result["team1Names"] == ["Leo"]
    assert result["team2Names"] == ["Khanh"]
    assert result["tournament"] == "Summer Cup"
    assert "Leo vs Khanh" in result["title"]
    assert "Summer Cup" in result["title"]
    assert "#sunbadminton" in result["description"]


@patch("video_prep.datetime")
def test_create_metadata_doubles(mock_datetime):
    mock_datetime.now.return_value.strftime.return_value = "2024-12-15"
    video_path = Path("md_DenzTuvsHuyzHa.mov")

    result = create_metadata(video_path)

    assert result["matchType"] == "Men's Doubles"
    assert result["team1Names"] == ["Den", "Tu"]
    assert result["team2Names"] == ["Huy", "Ha"]
    assert result["tournament"] == "Cafe Game"
    assert "Den/Tu vs Huy/Ha" in result["title"]
