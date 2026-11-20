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

# Upload mode chosen in the editor -> YouTube privacy. Privacy is the only
# thing the two modes differ in.
MODES = {"dev": "private", "production": "public"}
DEFAULT_MODE = "dev"
# YouTube rejects longer titles, and titles containing < or >.
MAX_TITLE_LENGTH = 100
