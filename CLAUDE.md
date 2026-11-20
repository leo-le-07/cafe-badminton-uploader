# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

A local web app for cutting badminton match recordings and uploading each match to YouTube. `uv run main.py` starts a Flask server on `127.0.0.1` and opens a browser editor. The user ticks recordings from `INPUT_DIR` (they join into one timeline in recording order), marks each match's segments on the timeline with the keyboard, types the players' names and presses one button. A background queue in the same process then builds metadata and a thumbnail, cuts and joins the segments with overlays in one ffmpeg encode, uploads to YouTube, sets the thumbnail and archives the match.

## Development Commands

```bash
uv sync                          # Install dependencies (ffmpeg/ffprobe must be on PATH)
uv run main.py                   # Run the editor (server + background queue, opens browser)
CAFE_NO_BROWSER=1 uv run main.py # Same, without opening a browser
uv run main.py auth              # YouTube OAuth; writes token.json
uv run main.py rethumbnail       # Re-render and re-set thumbnails from images dropped in COMPLETED_DIR workspaces

uv run pytest                    # Python tests
uv run pytest tests/test_jobs.py # A single test file
node --test tests/js/            # Frontend logic tests (model, names, save)
uv run ruff check .              # Lint
uv run ruff format .             # Format
```

`APP_ENV` picks the env file (`.env.dev` by default, `.env.production`); see `env.template` for the variables `config.py` reads.

## Safety

- `token.json` holds real YouTube credentials for the channel. While testing, never trigger a real enqueue (`POST /api/jobs`), upload, thumbnail set or login (`POST /api/auth/login`, `main.py auth`). Tests mock the YouTube API; keep it that way.
- Never modify, move or delete files in `INPUT_DIR`; they are the original recordings. Only the user's "Lưu trữ" action moves a source.
- Only one instance runs per `DATA_DIR`: `main.py` holds an exclusive `flock` on `DATA_DIR/app.lock` and exits with a message if another instance holds it. If the owner may be running the app, do not start a second one against the same `DATA_DIR`.

## Architecture

Everything runs in one Python process: no build step for the frontend (plain ES modules), no external services besides YouTube.

```
Browser editor (app/static, plain JS)
      │  HTTP, 127.0.0.1 only (default port 8790)
Flask server (app/server.py) ── page, original videos via HTTP Range, JSON API
      ├─ session.json   ticked sources, matches, segments (autosaved by the browser)
      ├─ players.json   player-name history for suggestions
      └─ JobQueue (app/jobs.py): one background thread, one step at a time
             └─ pipeline per match (app/pipeline.py):
                metadata → select_thumbnail → render_thumbnail
                → encode (cut + join + overlay, one ffmpeg run)
                → upload → set_thumbnail → cleanup
```

- Each queued match gets a workspace `DATA_DIR/workspaces/<match_id>/` with `job.json` (status, step, progress, error), `metadata.json`, `selected.jpg`, `thumbnail.jpg`, `processed.mov`, `upload.json` and, during upload, the resumable upload session. Each step skips itself if its output already exists, so a restart or "Thử lại" resumes where it stopped.
- Job statuses: `queued`, `running`, `waiting_quota`, `error`, `done`. A workspace with `upload.json` holding a video id is never uploaded again. An interrupted upload resumes the saved YouTube session. Quota errors put the job in `waiting_quota` and retry after `QUOTA_RETRY_HOURS` (and on every start); other jobs still run their pre-upload steps.
- Queued matches are locked in the editor; "Đưa về chỉnh sửa" removes a `queued`/`error` match that is not executing and has no YouTube video id and deletes its workspace.
- `cleanup` deletes `processed.mov` and the upload session, writes `segments.json`, and moves the workspace to `COMPLETED_DIR/<recorded_date>_<match_id>/`. Source files are only moved (to `COMPLETED_DIR/sources/`) when the user presses "Lưu trữ" on a source whose matches are all done.
- The title date is the recording date of the match's first source (`media_probe`), not the upload date. Privacy comes from `VIDEO_PRIVACY_STATUS` and is set at upload time.
- The editor plays the original `.mov`/`.mp4` files directly; there is no proxy. `/media/<name>` only serves files that are directly in `INPUT_DIR`.
- All JSON writes in `app/store.py` are atomic (temp file + `os.replace`); an unreadable file is renamed `*.corrupt-<timestamp>`, never deleted.

**Key files:**
- `main.py` — CLI entry point: no command = `serve()` (instance lock, bind port, start queue, open browser); `auth`, `rethumbnail`
- `config.py` — env loading: `INPUT_DIR`, `COMPLETED_DIR`, `DATA_DIR`, `APP_PORT`, `VIDEO_PRIVACY_STATUS`, `CANDIDATE_THUMBNAIL_NUM`, `LOGO_PATH`, `QUOTA_RETRY_HOURS`
- `app/models.py` — `Segment`, `Match`, `Session`, `Job` + validation; `JOB_STEPS`, `JOB_STATUSES`
- `app/store.py` — atomic JSON persistence: session, jobs, player names (seeded once from `COMPLETED_DIR/*/metadata.json`)
- `app/pipeline.py` — the per-match steps
- `app/jobs.py` — `JobQueue`: background thread, state machine, quota wait, retry, unqueue
- `app/server.py` — Flask app factory, JSON API (`/api/bootstrap`, `/api/session`, `/api/jobs`, `/api/sources/<name>/archive`, `/api/auth`), video streaming
- `app/static/js/` — `model.js` (pure segment/match/undo logic), `player.js` (multi-source playback on one time axis), `timeline.js` (draw, zoom, scrub, drag edges), `matches.js` (match cards and form), `names.js` (name suggestions), `queue.js` (upload button, queue), `auth.js` (sign-in state), `save.js` (autosave retry policy), `api.js`, `main.js` (wiring, shortcuts, autosave)
- `media_probe.py` — ffprobe: duration, fps, display size, audio, recording time
- `video_prep.py` — title/description/tags from form fields; thumbnail frame selection within a match's segments
- `video_overlay.py` — CAFE GAME / THANKS FOR WATCHING overlays and logo; builds the single ffmpeg command from segments (`h264_videotoolbox`, falls back to `libx264`)
- `thumbnail_enhancement/renderer.py` — renders the styled thumbnail (template B by default)
- `uploader.py` — resumable YouTube upload (saved session), quota error classification, thumbnail setting, `upload.json`
- `cleanup.py` — archive a finished workspace; archive a source file
- `rethumbnail.py` — re-render/re-set thumbnails for archived workspaces (old and new layouts)
- `auth_service.py` — OAuth (`client_secret.json` → `token.json`), cached sign-in status, background login for the editor
- `tests/` — pytest suite (`conftest.py` points `INPUT_DIR`/`COMPLETED_DIR`/`DATA_DIR` at temp paths); `tests/js/` — Node test runner suite
