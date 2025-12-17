# Cafe Badminton Video Uploader

A CLI tool to batch process and upload badminton match videos to YouTube with auto-generated thumbnails.

## Setup

1. Install dependencies: `uv sync`
2. Copy `env.template` to `.env` and adjust values
3. Place `client_secret.json` (YouTube API credentials) in root

## Video filename format

```
{matchType}_{team1}vs{team2}_{tournament}.mov
```

- matchType: ms, md, ws, wd, xd (singles/doubles)
- team names: separated by `z` for doubles (e.g., `KhanhzLeo`)
- tournament: optional, defaults to "Cafe Game"

Examples:
- `md_NhozVinhvsKhanhzLeo.MOV`
- `xd_KhanhzVyvsZezTram_Friendly Game.mov`

## Usage

Run all stages at once:
```
uv run main.py all
```

Or run individual stages:
```
uv run main.py prepare   # extract frames, create metadata
uv run main.py select    # pick thumbnail (H/L to navigate, Enter/S to select)
uv run main.py enhance   # render final thumbnail with graphics
uv run main.py upload    # upload to YouTube
uv run main.py cleanup   # move uploaded files to completed folder
```

Template option for enhance stage:
```
uv run main.py enhance --template template_b
```

