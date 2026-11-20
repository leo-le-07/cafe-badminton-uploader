import pytest

from video_prep import (
    create_title,
    _format_team_names,
    _create_tag,
    create_description,
    create_metadata_from_fields,
)


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


def test_metadata_from_fields_matches_existing_format():
    m = create_metadata_from_fields(
        "md", ["Nam", "Hùng"], ["Tú", "Long"], "Cafe Game", "2026-11-20"
    )
    assert m.title == "Nam/Hùng vs Tú/Long | Cafe Game (2026-11-20)"
    assert m.match_type == "Men's Doubles"
    assert m.team1_names == ["Nam", "Hùng"]
    assert m.team2_names == ["Tú", "Long"]
    assert m.tournament == "Cafe Game"
    assert "#mensdoubles" in m.description and "#cafegame" in m.description
    assert m.category == "17"


def test_metadata_keeps_tournament_as_typed():
    m = create_metadata_from_fields("ms", ["Leo"], ["Khanh"], "giải CLB mùa đông", "2026-11-20")
    assert m.tournament == "giải CLB mùa đông"
    assert m.title == "Leo vs Khanh | giải CLB mùa đông (2026-11-20)"


def test_metadata_rejects_unknown_match_type():
    with pytest.raises(ValueError):
        create_metadata_from_fields("zz", ["A"], ["B"], "X", "2026-01-01")
