MATCH_TYPES = {
    "ms": "Men's Singles",
    "md": "Men's Doubles",
    "ws": "Women's Singles",
    "wd": "Women's Doubles",
    "xd": "Mixed Doubles",
}

FIXED_TAGS = "#sunbadminton #badminton #cafebadminton"
CATEGORY_SPORTS = "17"
DEFAULT_TOURNAMENT = "Cafe Game"

# Thumbnail sidebar colours (RGB). The default tournament always uses
# CAFE_GAME_THEME; any other tournament uses one of TOURNAMENT_THEMES, picked
# in the editor (the first one when none is picked).
THEME_COLORS = {
    "blue": (0, 60, 150),
    "purple": (85, 30, 130),
    "red": (150, 20, 35),
    "green": (10, 95, 60),
    "orange": (205, 95, 10),
    "teal": (0, 110, 120),
}
CAFE_GAME_THEME = "blue"
TOURNAMENT_THEMES = ("purple", "red", "green", "orange", "teal")

# Upload mode chosen in the editor -> YouTube privacy. Privacy is the only
# thing the two modes differ in.
MODES = {"dev": "private", "production": "public"}
DEFAULT_MODE = "dev"
# YouTube rejects longer titles, and titles containing < or >.
MAX_TITLE_LENGTH = 100
