# Cafe Badminton Video Uploader

A local web app that cuts badminton match recordings into one video per match and uploads them to YouTube with a generated title, description, overlays and thumbnail.

You open the editor in the browser, tick the recordings, mark where each match starts and stops on a timeline, type the players' names and press one button. The app does the rest in the background: one match at a time, it encodes, uploads, sets the thumbnail and archives.

## Setup

1. Install system dependencies: `brew install ffmpeg` (provides `ffmpeg` and `ffprobe`).
2. Install Python dependencies: `uv sync` (Python 3.13+).
3. Create an environment file: copy `env.template` to `.env.dev` (or `.env.production`, used with `APP_ENV=production`) and adjust the values. See [Configuration](#configuration).
4. Place `client_secret.json` (Google OAuth client for the YouTube Data API) in the project root.

## Sign in to YouTube

```bash
uv run main.py auth
```

Opens the browser for Google OAuth and saves the token to `token.json` in the project root. You can also sign in from the editor: when you are signed out, the top bar shows "○ YouTube chưa đăng nhập" with a "Đăng nhập YouTube" button that starts the same flow.

Matches cannot be queued while you are signed out. If the token expires during processing, the match stops with an error asking you to sign in again and press "Thử lại".

## Run

```bash
uv run main.py                              # uses .env.dev
APP_ENV=production uv run main.py           # uses .env.production
```

This starts the editor at `http://127.0.0.1:8790/` (port from `APP_PORT`) and opens it in your browser after a second. Set `CAFE_NO_BROWSER=1` to skip opening the browser. Stop the app with `Ctrl+C`.

The server only listens on `127.0.0.1`. Closing the browser tab does not stop the queue; stopping the process does, and the next start continues from the unfinished step.

## Using the editor

The page has three columns:

- **Left: sources.** The `.mov` / `.mp4` files directly in `INPUT_DIR`, with duration and recording time. Ticked files are joined into one continuous timeline in recording order, with a separator and the file name at each join. Unticking a file that has marked segments asks for confirmation, because those segments are deleted.
- **Middle: player and timeline.** The video always shows the frame under the yellow playhead. The thin bar on top shows the whole timeline; click it to jump. In the detail view below, drag with the left mouse button to scrub, drag a segment's white edge to adjust a cut point, and zoom with the slider, the `+` / `−` buttons or keys, or `⌘`/`Ctrl` + mouse wheel. "Vừa màn hình" zooms back out to fit everything.
- **Right: matches and queue.** One card per match, the "Xử lý & upload N trận đã đủ thông tin" button and the queue.

### Marking matches

A match is a list of segments `(source file, in point, out point)`. Anything not inside a segment is dropped (shown as grey stripes).

- Press `I` to start a segment of the selected match at the playhead and `O` to close it. Press `N` to close the open segment (if any) and start a new match.
- To drop a stretch in the middle of a match (a break, a long pause), press `O` where it starts and `I` where it ends. The match then has two segments.
- A match split across two recordings: tick both files and mark the segments on both sides of the join. An open segment that runs across a join is split into two segments of the same match automatically.
- Click a match card (or one of its segments on the timeline) to select it; `I` / `O` then add segments to that match.
- `I` inside a closed segment of the selected match moves that segment's in point to the playhead; `O` moves its out point.
- Segments never overlap, even across matches; an edit that would overlap stops at the neighbouring segment's edge.
- Every change to segments or matches can be undone with `⌘Z`.
- A segment you opened with `I` is saved too: closing the tab or restarting the app keeps it open where you left it. A match with an open segment cannot be queued until you close it with `O`.

### Keyboard shortcuts

| Key | Action |
|---|---|
| `I` | Start a new segment of the selected match at the playhead |
| `O` | Close the open segment at the playhead |
| `N` | Close the open segment (if any), create a new match and select it |
| `Space` | Play / pause |
| `J` `K` `L` | Reverse / stop / forward. Press `L` again for 2×, 4×, 8× |
| `←` `→` | Back / forward 1 second |
| `⇧←` `⇧→` | Back / forward 10 seconds |
| `,` `.` | Back / forward 1 frame |
| `+` `−` | Zoom the timeline |
| `⌘Z` (`Ctrl+Z`) | Undo |
| `Enter` | Jump to the player-name field of the selected match |
| `Delete` or `Backspace` | Delete the segment under the playhead |

Shortcuts are ignored while you type in a field; `Esc` leaves the field and returns to the editor. `Enter` and `Space` on a focused button activate the button instead.

### Match details

Each match card has:

- **Match type:** MS, MD, WS, WD, XD. A new match takes the type of the previous one.
- **Two teams:** type a name and press `Enter` or `,` to add it as a chip; `Tab` moves to the other team. Suggestions come from names used before, most used first. On the first run the history is seeded from the `metadata.json` files already in `COMPLETED_DIR`.
- **Tournament:** defaults to "Cafe Game"; left empty, the title uses "Cafe Game" too.
- A preview of the YouTube title, e.g. `Nam/Hùng vs Tú/Long | Cafe Game (2026-11-20)`. The date is the recording date of the match's first source file, not the upload date.
- The number of segments and the total length after cutting. A match shows a warning and cannot be queued when it has no segments, a missing name on either side, a segment still open, a title longer than 100 characters, or a name or tournament containing `<` or `>` (YouTube rejects those two titles).

Everything autosaves to `DATA_DIR/session.json` within a few seconds; the top bar shows the save state. Reopening the app restores the same session.

Each `uv run main.py` opens a new tab, so older tabs can pile up. Only the tab that has the latest session can save: if another tab saved in the meantime, an older tab shows a red bar "Phiên đã được thay đổi ở tab khác…" with a "Tải lại" button, stops saving and disables its upload and archive buttons. Its unsaved edits are not written over the newer work; reload it to continue.

## What happens after pressing upload

"Xử lý & upload N trận đã đủ thông tin" queues every complete match. Queued matches are locked; you can keep marking other matches while the queue runs. Matches are processed one at a time, in order, through these steps:

1. **metadata:** title, description and tags from the form.
2. **select_thumbnail:** scores frames sampled from the match's segments and picks the best one.
3. **render_thumbnail:** draws the styled thumbnail.
4. **encode:** one ffmpeg run cuts the segments from the original files, joins them and adds the logo plus the CAFE GAME (first 12 seconds) and THANKS FOR WATCHING (last 12 seconds, if the match is longer than 24 seconds) overlays. Uses `h264_videotoolbox`, falling back to `libx264`.
5. **upload:** resumable upload with privacy `VIDEO_PRIVACY_STATUS`.
6. **set_thumbnail**
7. **cleanup:** archives the match (see below).

Each queue row shows the current step and percentage for encode and upload, and a YouTube link when done.

- **Error:** the row shows the message (long ones scroll; hover for the full text) and a "Thử lại" button, which resumes from the failed step. The queue moves on to the next match.
- **Network blips during upload** are retried automatically on the same upload session (up to five times, with a growing pause) before the match stops with an error.
- **YouTube quota exceeded** (while uploading or while setting the thumbnail): the match shows "Chờ quota YouTube, sẽ tự thử lại" and is retried every `QUOTA_RETRY_HOURS` hours while the app runs, and on every start. Later matches still do their steps up to upload, then wait too. "Thử lại" retries immediately.
- **Interrupted upload** (app stopped, crash, network down): once the first 16 MB chunk has gone through, the upload session is saved, and the next attempt resumes that same YouTube session instead of creating a new video. A match that already has a YouTube video id is never uploaded again. Two cases can still produce a duplicate video: the saved session has expired (YouTube keeps it for about a week), so the upload starts over although the earlier one may have finished; or the encoded file is 16 MB or smaller, so it goes up in one chunk and no session is saved before YouTube has the whole video. If in doubt, check the channel before pressing "Thử lại".
- **"Đưa về chỉnh sửa":** on a queued ("Đang chờ"), failed or quota-waiting match that is not on YouTube yet and not being processed right now, removes it from the queue, deletes its partial work and unlocks it for editing. It is refused while an upload session exists (the video may already be complete on YouTube): press "Thử lại" first so the upload finishes. Once a match has a YouTube video id, edit it on YouTube instead.
- **Unreadable `upload.json`** in a workspace: the match stops with an error and is never uploaded again automatically; check on YouTube whether the video is there, then fix or delete the file and press "Thử lại".
- If the editor cannot reach the app (it was stopped), the queue shows "Mất kết nối với ứng dụng — đang thử lại…" and greys the rows until it can again.

## Where files end up

- While processing: `DATA_DIR/workspaces/<match_id>/`.
- After a match is done: its workspace moves to `COMPLETED_DIR/<recording date>_<match_id>/` with `metadata.json`, `selected.jpg`, `thumbnail.jpg`, `upload.json`, `job.json` and `segments.json` (the cut list, so the video can be rebuilt from the sources). The encoded video is deleted after upload.
- Source recordings stay in `INPUT_DIR`. When every match that uses a source is done, that source shows a "Lưu trữ" button in the left column; pressing it moves the file to `COMPLETED_DIR/sources/` and removes it from the session.

## Replace a thumbnail

To use your own thumbnail image for an uploaded match, drop the image (for example `.jpg` or `.png`) into that match's folder in `COMPLETED_DIR`, then run:

```bash
uv run main.py rethumbnail
```

For every folder in `COMPLETED_DIR` that has an upload record and a dropped image, it renders the image through the thumbnail template, sets it on YouTube and deletes the dropped image. Works for folders from the old version of the app as well.

## Configuration

Variables in `.env.dev` / `.env.production` (see `env.template`):

| Variable | Default | Meaning |
|---|---|---|
| `INPUT_DIR` | required | Folder with the recordings (`.mov`, `.mp4`). Created if missing |
| `COMPLETED_DIR` | required | Archive of finished matches and archived sources. Created if missing |
| `DATA_DIR` | `./data` | Session, player-name history and workspaces of matches in progress |
| `APP_PORT` | `8790` | Port of the editor on `127.0.0.1` |
| `VIDEO_PRIVACY_STATUS` | `private` | `public`, `unlisted` or `private`; applies to every upload |
| `CANDIDATE_THUMBNAIL_NUM` | `10` | Frames sampled per match when picking the thumbnail |
| `LOGO_PATH` | `assets/logo.png` | Logo burned into the video (skipped with a warning if missing) |
| `QUOTA_RETRY_HOURS` | `4` | Wait before retrying after a YouTube quota error |

Outside the env file: `APP_ENV` picks the env file (`dev` by default), `CAFE_NO_BROWSER=1` skips opening the browser, `LOG_LEVEL` sets log verbosity (`INFO` by default).

## Troubleshooting

**"Ứng dụng đã đang chạy với thư mục dữ liệu …"**
Another instance of the app is already running with the same `DATA_DIR` (only one may run at a time). Open the URL in the message in your browser, or stop the other instance first.

**"Không mở được cổng 8790 trên 127.0.0.1 …"**
Another program uses the port. Set `APP_PORT` to a different port in your `.env` file and run again.

## Development

```bash
uv run pytest                 # Python tests (YouTube API is always mocked; APP_ENV=test, temp folders only)
node --test tests/js/         # Frontend logic tests
uv run ruff check .           # Lint
uv run ruff format .          # Format
uv run pytest --cov=. --cov-report=term-missing -q  # Coverage summary
```
