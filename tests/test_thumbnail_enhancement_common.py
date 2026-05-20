from pathlib import Path

from PIL import Image

from thumbnail_enhancement.common import (
    STYLE_BLUE,
    STYLE_PURPLE,
    STYLE_WHITE,
    add_logo,
    enhance_image_visuals,
    format_matchup_text,
    format_team_name,
    get_theme_for_tournament,
)


class TestGetThemeForTournament:
    def test_empty_string_returns_blue(self):
        assert get_theme_for_tournament("") == STYLE_BLUE

    def test_cafe_game_returns_blue(self):
        assert get_theme_for_tournament("cafe game") == STYLE_BLUE

    def test_friendly_game_returns_white(self):
        assert get_theme_for_tournament("friendly game") == STYLE_WHITE

    def test_tournament_returns_purple(self):
        assert get_theme_for_tournament("tournament") == STYLE_PURPLE

    def test_tour_prefix_returns_purple(self):
        assert get_theme_for_tournament("Tour 2024") == STYLE_PURPLE

    def test_tournament_prefix_returns_purple(self):
        assert get_theme_for_tournament("Tournament Finals") == STYLE_PURPLE

    def test_unknown_name_returns_blue(self):
        assert get_theme_for_tournament("random league") == STYLE_BLUE

    def test_leading_and_trailing_whitespace_normalised(self):
        assert get_theme_for_tournament("  cafe game  ") == STYLE_BLUE


class TestFormatTeamName:
    def test_single_name_uppercased(self):
        assert format_team_name(["leo"]) == "LEO"

    def test_multiple_names_joined_by_slash_space(self):
        assert format_team_name(["den", "tu"]) == "DEN / TU"

    def test_already_uppercase_unchanged(self):
        assert format_team_name(["LEO"]) == "LEO"


class TestFormatMatchupText:
    def test_singles_matchup(self):
        assert format_matchup_text(["leo"], ["khanh"]) == "LEO vs KHANH"

    def test_doubles_matchup(self):
        assert (
            format_matchup_text(["den", "tu"], ["huy", "ha"]) == "DEN / TU vs HUY / HA"
        )


class TestEnhanceImageVisuals:
    def test_returns_rgb_image_of_same_size(self):
        img = Image.new("RGB", (320, 180), (100, 150, 200))
        result = enhance_image_visuals(img)
        assert result.mode == "RGB"
        assert result.size == (320, 180)

    def test_accepts_rgba_input(self):
        img = Image.new("RGBA", (320, 180), (100, 150, 200, 255))
        result = enhance_image_visuals(img)
        assert result.mode == "RGB"

    def test_accepts_greyscale_converted_to_rgb(self):
        img = Image.new("L", (320, 180), 128).convert("RGB")
        result = enhance_image_visuals(img)
        assert result.mode == "RGB"


class TestAddLogo:
    def test_returns_image_when_logo_missing(self, tmp_path):
        img = Image.new("RGB", (320, 180), (100, 150, 200))
        result = add_logo(img, tmp_path / "nonexistent.png")
        assert result.size == img.size

    def test_composites_real_logo_and_returns_image(self):
        img = Image.new("RGB", (320, 180), (100, 150, 200))
        result = add_logo(img, Path("assets/logo.png"))
        assert result.size == (320, 180)
        assert result.mode in ("RGB", "RGBA")
