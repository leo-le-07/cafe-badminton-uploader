# Cafe Badminton Video Uploader

A CLI tool to batch process and upload badminton match videos to YouTube with auto-generated thumbnails.

## Setup

1. Install dependencies: `uv sync`
2. Create environment files:
   - Copy `env.template` to `.env.dev` for development
   - Copy `env.template` to `.env.production` for production
   - Adjust values in each file
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

### Environment Selection

The tool supports multiple environment configurations via `APP_ENV`:

**Development (default):**
```bash
uv run main.py all
# or explicitly:
APP_ENV=dev uv run main.py all
```

**Production:**
```bash
APP_ENV=production uv run main.py all
```

### Running All Stages

```bash
uv run main.py all
```

### Individual Stages

```bash
uv run main.py prepare   # extract frames, create metadata
uv run main.py rank      # rank thumbnails using CLIP
uv run main.py select    # pick thumbnail (H/L to navigate, Enter/S to select)
uv run main.py enhance   # render final thumbnail with graphics
uv run main.py upload    # upload to YouTube
uv run main.py cleanup   # move uploaded files to completed folder
```

### Template Option for Enhance Stage

```bash
uv run main.py enhance --template template_b
```

### Running Module Scripts

For development/testing, you can run modules directly:

```bash
# Development environment (default)
uv run python -m thumbnail_ranking.pipeline

# Production environment
APP_ENV=production uv run python -m thumbnail_ranking.pipeline
```

