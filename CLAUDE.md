# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A CLI tool that automates batch processing and uploading of badminton match videos to YouTube. It scans a local input directory, parses metadata from video filenames, uploads to YouTube, generates thumbnails via a web UI, enhances them with styled overlays, and archives completed videos.

## Development Commands

```bash
uv sync                          # Install dependencies
uv run pytest                           # Run all tests
uv run pytest tests/test_video_prep.py  # Run a specific test file
uv run ruff check .                     # Lint
uv run ruff format .                    # Format
```

### Running Locally (3 terminals required)

```bash
# Terminal 1: Temporal server
temporal server start-dev

# Terminal 2: Worker process
uv run main.py worker

# Terminal 3: CLI commands
uv run main.py auth              # Authenticate with YouTube (OAuth)
uv run main.py start             # Start workflows for videos in INPUT_DIR
uv run main.py list              # List waiting for select thumbnail workflows 
uv run main.py select            # Open web UI for thumbnail selection
```

## Architecture

The pipeline is orchestrated by **Temporal** (distributed workflow engine). Each video goes through a `ProcessVideoWorkflow` with these stages:

```
INITIALIZING → CREATING_METADATA → UPLOADING → UPDATING_VISIBILITY
→ WAITING_FOR_SELECTION  ← (pauses here, waits for signal)
→ SELECTED → ENHANCING_THUMBNAIL → SETTING_THUMBNAIL → COMPLETED
```

The workflow pauses at `WAITING_FOR_SELECTION` using Temporal's `wait_condition()`. The user runs `uv run main.py select`, which starts a Flask server. The user selects a thumbnail frame in the browser, which sends a `thumbnail_selected` signal to the workflow, allowing it to resume.

**Key files:**
- `main.py` — CLI entry point (commands: auth, start, list, select, worker, debug)
- `temporal/workflows.py` — `ProcessVideoWorkflow` class; workflow stages and signal handling
- `temporal/activities.py` — Individual activity functions (each pipeline step)
- `temporal/worker.py` — Worker process; task queue: `badminton-video-processing`
- `video_prep.py` — Parses video filenames → generates YouTube title/description/metadata JSON
- `uploader.py` — Resumable YouTube uploads (16MB chunks), thumbnail setting, visibility updates
- `web_selector/server.py` — Flask server; streams video, receives selected frame from browser
- `thumbnail_enhancement/renderer.py` — Selects template A or B and renders styled overlay
- `config.py` — All env var loading
- `schemas.py` — Dataclasses: `MatchMetadata`, `UploadedRecord`, `ChannelInfo`
