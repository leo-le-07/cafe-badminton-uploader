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
   APP_ENV=production uv run main_temporal.py worker
   ```
   Keep this running in a separate terminal. The worker will process workflows and activities.

### Environment Selection

The tool supports multiple environment configurations via `APP_ENV`:

```bash
APP_ENV=production uv run main_temporal.py start
```

### CLI Commands

#### Authenticate with YouTube

```bash
uv run main_temporal.py auth
```
Opens browser for OAuth authentication and saves token for future use.

#### Start Workflows

```bash
uv run main_temporal.py start
```
Scans the input directory and starts a workflow for each video found. All workflows will be processed concurrently by the worker.

#### List Pending Workflows

```bash
uv run main_temporal.py list
```
Lists all workflows that are waiting for thumbnail selection.

#### Select Thumbnails

```bash
uv run main_temporal.py select
```

