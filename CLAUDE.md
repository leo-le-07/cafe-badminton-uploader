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
node --test tests/js/            # Frontend logic tests (model, names, save, queue)
uv run ruff check .              # Lint
uv run ruff format .             # Format
```

`config.py` loads the single env file `.env`; see `env.template` for the variables it reads. Dev or Production is chosen in the editor, not at start-up: any `APP_ENV` other than `test` is ignored with a warning. `APP_ENV=test` loads no env file at all and reads only the process environment: `tests/conftest.py` sets it, with `INPUT_DIR`, `COMPLETED_DIR` and `DATA_DIR` pointing at fresh temp folders, before anything imports `config`.

## Safety

- `token.json` holds real YouTube credentials for the channel. While testing, never trigger a real enqueue (`POST /api/jobs`), upload, thumbnail set or login (`POST /api/auth/login`, `main.py auth`). Tests mock the YouTube API; keep it that way.
- Never modify, move or delete files in `INPUT_DIR`; they are the original recordings. Only the user's "Lưu trữ" (to `COMPLETED_DIR/sources/`) and "Xoá" (to the macOS trash, `~/.Trash`) actions move a source. Tests point `cleanup.TRASH_DIR` at a temp folder (autouse fixture in `tests/conftest.py`); keep it that way.
- Only one instance runs per `DATA_DIR`: `main.py` holds an exclusive `flock` on `DATA_DIR/app.lock` and exits with a message if another instance holds it. If the owner may be running the app, do not start a second one against the same `DATA_DIR`.

## Architecture

Everything runs in one Python process: no build step for the frontend (plain ES modules), no external services besides YouTube.

```
Browser editor (app/static, plain JS)
      │  HTTP, 127.0.0.1 only (default port 8790)
Flask server (app/server.py) ── page, original videos via HTTP Range, JSON API
      ├─ session.json   ticked sources, matches, segments, open point, revision (autosaved by the browser)
      ├─ mode.json      mode last chosen in the editor: dev or production
      ├─ players.json   player-name history for suggestions
      └─ JobQueue (app/jobs.py): one background thread, one step at a time
             └─ pipeline per match (app/pipeline.py):
                metadata → select_thumbnail → render_thumbnail
                → encode (cut + join + overlay, one ffmpeg run)
                → upload → set_thumbnail → cleanup
```

- Each queued match gets a workspace `DATA_DIR/workspaces/<match_id>/` with `job.json` (status, step, progress, error), `metadata.json`, `selected.jpg`, `thumbnail.jpg`, `processed.mov`, `upload.json` and, during upload, the resumable upload session. Each step skips itself if its output already exists, so a restart or "Thử lại" resumes where it stopped.
- The editor has a Dev / Production switch. The two modes differ only in upload privacy (`constants.MODES`: dev = private, production = public); keep it that way unless the owner asks for more. `mode.json` holds the current mode (`PUT /api/mode`; missing or unusable = dev). `POST /api/jobs` must carry the mode shown in the editor; it is stored in each `job.json` and the upload step reads the privacy from the job, so moving the switch never changes a queued match. A `job.json` without a known mode counts as dev.
- Job statuses: `queued`, `running`, `waiting_quota`, `error`, `done`. A workspace with `upload.json` holding a video id is never uploaded again. An interrupted upload resumes the saved YouTube session. Quota errors put the job in `waiting_quota` and retry after `QUOTA_RETRY_HOURS` (and on every start); other jobs still run their pre-upload steps.
- Queued matches are locked in the editor; "Đưa về chỉnh sửa" removes a `queued`/`error`/`waiting_quota` match that is not executing, has no YouTube video id and no resumable upload session (`upload_session.json`), and deletes its workspace.
- `session.json` carries `revision` (bumped by every server-side write) and `open` (`{match_id, source, time}`, the pending `I` point, time local to the source). `PUT /api/session` must send the revision it was based on; otherwise 409 `{"errors": [...], "code": "stale_revision"}` and nothing is stored. The client then stops saving and shows a reload banner. A match owning the open point cannot be queued.
- Every mutating `/api/*` request (POST/PUT/PATCH/DELETE) must carry `X-Cafe-Editor: 1` (403 otherwise); `api.js` sends it. This stops other websites from triggering actions with simple cross-origin POSTs.
- `upload.json` and the upload session are written atomically; an unreadable `upload.json` raises `CorruptUploadRecordError` and turns the job into an error (never an upload). At startup, archives in `COMPLETED_DIR` whose `upload.json` holds a video id stay locked even if their `job.json` is missing or unreadable.
- Problems that block queuing (`match_problems` in Python, `matchProblems` in JS) must stay word for word identical; `tests/test_rules_parity.py` runs the same cases through both.
- `cleanup` deletes `processed.mov` and the upload session, writes `segments.json`, and moves the workspace to `COMPLETED_DIR/<recorded_date>_<match_id>/`. Source files are only moved (to `COMPLETED_DIR/sources/`) when the user presses "Lưu trữ" on a source whose matches are all done, or to the trash when the user presses "Xoá" on a source that no unfinished match (in the editor or the queue) uses.
- The title date is the recording date of the match's first source (`media_probe`), not the upload date. Privacy comes from the job's mode and is set at upload time.
- The editor plays the original `.mov`/`.mp4` files directly; there is no proxy. `/media/<name>` only serves files that are directly in `INPUT_DIR`.
- All JSON writes in `app/store.py` are atomic (temp file + `os.replace`); an unreadable file is renamed `*.corrupt-<timestamp>`, never deleted.

**Key files:**
- `main.py` — CLI entry point: no command = `serve()` (instance lock, bind port, start queue, open browser); `auth`, `rethumbnail`
- `config.py` — env loading: `INPUT_DIR`, `COMPLETED_DIR`, `DATA_DIR`, `APP_PORT`, `CANDIDATE_THUMBNAIL_NUM`, `LOGO_PATH`, `QUOTA_RETRY_HOURS`
- `app/models.py` — `Segment`, `Match`, `OpenPoint`, `Session`, `Job` + validation; `JOB_STEPS`; `match_problems`, `match_title`
- `app/store.py` — atomic JSON persistence: session, mode, jobs, player names (seeded once from `COMPLETED_DIR/*/metadata.json`)
- `app/pipeline.py` — the per-match steps
- `app/jobs.py` — `JobQueue`: background thread, state machine, quota wait, retry, unqueue
- `app/server.py` — Flask app factory, JSON API (`/api/bootstrap`, `/api/session`, `/api/mode`, `/api/jobs`, `/api/sources/<name>/archive`, `/api/sources/<name>/delete`, `/api/auth`), video streaming
- `app/static/js/` — `model.js` (pure segment/match/undo logic), `player.js` (multi-source playback on one time axis), `timeline.js` (draw, zoom, scrub, drag edges), `matches.js` (match cards and form), `names.js` (name suggestions), `queue.js` (upload button, queue), `auth.js` (sign-in state), `mode.js` (Dev / Production switch), `save.js` (autosave retry and stale-session policy), `format.js` (shared text helpers), `api.js`, `main.js` (wiring, shortcuts, autosave)
- `media_probe.py` — ffprobe: duration, fps, display size, audio, recording time
- `video_prep.py` — title/description/tags from form fields; thumbnail frame selection within a match's segments
- `video_overlay.py` — CAFE GAME / THANKS FOR WATCHING overlays and the logo watermark (top right, with CAFE BADMINTON under it, composed into one PNG by `render_logo_badge`) (CAFE and GAME are separate full-frame PNGs that overlay slides in and out with a time-based x; THANKS zooms in from the centre: its PNG is looped for the outro and scaled per frame; the intro never uses a looped input, which would add frames to short videos); builds the single ffmpeg command from segments (`h264_videotoolbox`, falls back to `libx264`). Each segment is seeked half a frame early (its own source's fps) and its timestamps restart at 0, so the cut keeps exactly the frames from `start` up to, not including, `end`; `tests/test_render_integration.py` checks this on frame-numbered clips
- `thumbnail_enhancement/renderer.py` — renders the styled thumbnail (template B by default)
- `uploader.py` — resumable YouTube upload (saved session, `num_retries=5`, dropped connections retried on the same session), quota error classification (upload and thumbnail), thumbnail setting, `upload.json`
- `cleanup.py` — archive a finished workspace; archive a source file or move it to the trash
- `rethumbnail.py` — re-render/re-set thumbnails for archived workspaces (old and new layouts)
- `auth_service.py` — OAuth (`client_secret.json` → `token.json`), cached sign-in status, background login for the editor
- `tests/` — pytest suite (`conftest.py` sets `APP_ENV=test` and points `INPUT_DIR`/`COMPLETED_DIR`/`DATA_DIR` at temp paths); `tests/js/` — Node test runner suite (model, names, save, queue, mode)
