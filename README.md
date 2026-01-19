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

### Prerequisites

1. **Start Temporal Server** (required for workflow execution):
   ```bash
   temporal server start-dev
   ```
   This starts a local Temporal development server. Keep this running in a separate terminal.

2. **Start the Worker** (required to process workflows):
   ```bash
   APP_ENV=production uv run main.py worker
   ```
   Keep this running in a separate terminal. The worker will process workflows and activities.

### Environment Selection

The tool supports multiple environment configurations via `APP_ENV`:

```bash
APP_ENV=production uv run main.py start
```

### CLI Commands

#### Authenticate with YouTube

```bash
uv run main.py auth
```
Opens browser for OAuth authentication and saves token for future use.

#### Start Workflows

```bash
uv run main.py start
```
Scans the input directory and starts a workflow for each video found. All workflows will be processed concurrently by the worker.

#### List Pending Workflows

```bash
uv run main.py list
```
Lists all workflows that are waiting for thumbnail selection.

**Note**: With the new web-based thumbnail selector, the browser opens automatically when a workflow reaches the selection stage. The `list` command is still available for monitoring purposes.

#### Debug Individual Steps

```bash
uv run main.py debug <step> <video_path>
```

Run individual workflow steps for debugging without executing the full workflow. Available steps:
- `metadata` - Create and store video metadata
- `upload` - Upload video to YouTube
- `select-thumbnail` - Open web-based thumbnail selector (opens browser automatically)
- `render` - Render final thumbnail
- `set-thumbnail` - Set thumbnail for uploaded video
- `update-visibility` - Update video visibility
- `cleanup` - Move video to completed directory

Example:
```bash
uv run main.py debug metadata input/md_HuyzVietvsThezLeo.mov
```

### Web-Based Thumbnail Selection

The thumbnail selection process uses a web-based UI that:
- Opens automatically when a workflow reaches the selection stage
- Provides a smooth horizontal timeline scrubber for frame navigation
- Extracts frames client-side using HTML5 video and canvas (no server round-trips)
- Allows precise frame selection by scrubbing through the entire video
- Works with `.mov` and `.MOV` video files

**Testing the thumbnail selector independently:**
```bash
uv run python -m web_selector.test_thumbnail_selector <video_path>
```

This allows you to test the thumbnail selector UI without running the full workflow.
