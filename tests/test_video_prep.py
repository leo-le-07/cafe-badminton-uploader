import pytest
from freezegun import freeze_time


from video_prep import (
    parse_filename,
    create_title,
    _format_team_names,
)


@pytest.mark.parametrize(
    "filename, expected",
    [
        # Case: Men's Singles (Default Tournament)
        (
            "ms_LeovsKhanh.mp4",
            {
                "matchType": "Men's Singles",
                "team1Names": ["Leo"],
                "team2Names": ["Khanh"],
                "tournament": "Cafe Game",
            },
        ),
        # Case: Women's Singles (Default Tournament)
        (
            "ws_AnhvsMai.mp4",
            {
                "matchType": "Women's Singles",
                "team1Names": ["Anh"],
                "team2Names": ["Mai"],
                "tournament": "Cafe Game",
            },
        ),
        # Case: Men's Doubles (Multiple players via 'z')
        (
            "md_DenzTuvsHuyzHa.mp4",
            {
                "matchType": "Men's Doubles",
                "team1Names": ["Den", "Tu"],
                "team2Names": ["Huy", "Ha"],
                "tournament": "Cafe Game",
            },
        ),
        # Case: Women's Doubles
        (
            "wd_AnhzMaivsLinhzHoa.mp4",
            {
                "matchType": "Women's Doubles",
                "team1Names": ["Anh", "Mai"],
                "team2Names": ["Linh", "Hoa"],
                "tournament": "Cafe Game",
            },
        ),
        # Case: Mixed Doubles + Explicit Tournament
        (
            "xd_DenzAnhvsHuyzMai_Sunbad Tour Game.mp4",
            {
                "matchType": "Mixed Doubles",
                "team1Names": ["Den", "Anh"],
                "team2Names": ["Huy", "Mai"],
                "tournament": "Sunbad Tour Game",
            },
        ),
        # Case: Singles + Explicit Tournament (Year)
        (
            "ms_LeovsKhanh_Summer Cup 2024.mp4",
            {
                "matchType": "Men's Singles",
                "team1Names": ["Leo"],
                "team2Names": ["Khanh"],
                "tournament": "Summer Cup 2024",
            },
        ),
    ],
)
def test_parse_filename_valid(filename, expected):
    result = parse_filename(filename)
    assert result == expected


@pytest.mark.parametrize(
    "filename, error_match",
    [
        ("LeovsKhanh.mp4", "Invalid filename format"),
        ("invalid_LeovsKhanh.mp4", "Invalid match type"),
        ("ms_LeoKhanh.mp4", "Invalid teams format"),
        ("ms_Leo_vs_Khanh_vs_Extra.mp4", "Invalid teams format"),
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
    "metadata, expected",
    [
        (
            {
                "matchType": "Men's Singles",
                "team1Names": ["Anh"],
                "team2Names": ["Linh"],
                "tournament": "Winter League",
            },
            "Anh vs Linh | Winter League (01 Jan 2023)",
        )
    ],
)
@freeze_time("2023-01-01")
def test_create_title(metadata, expected):
    result = create_title(metadata)

    assert result == expected
