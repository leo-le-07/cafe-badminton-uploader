# Manual Thumbnail Replacement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `rethumbnail` CLI command that detects a manually dropped image in a completed video's workspace, re-renders it through the template pipeline, and sets it as the YouTube thumbnail.

**Architecture:** `rethumbnail.py` holds all detection and orchestration logic (for testability). `utils.get_workspace_dir` is fixed to derive workspace from the video path's own parent directory (not hardcoded `INPUT_DIR`), allowing functions to work with paths in `COMPLETED_DIR`. `main.py` adds the CLI subcommand that resolves the workspace and delegates to `rethumbnail.py`.

**Tech Stack:** Python stdlib (`pathlib`, `shutil`), existing `thumbnail_enhancement.renderer`, `uploader`, `auth_service`, `utils`.

---

### Task 1: Add `SUPPORTED_IMAGE_EXTENSIONS` constant to `utils.py`

**Files:**
- Modify: `utils.py:14` (alongside `SUPPORTED_VIDEO_EXTENSIONS`)
- Test: `tests/test_utils.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_utils.py` after the existing imports block:

```python
from utils import SUPPORTED_IMAGE_EXTENSIONS
```

Add a new test class after `TestScanVideos`:

```python
class TestSupportedImageExtensions:
    def test_contains_common_image_formats(self):
        for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".heic", ".heif"]:
            assert ext in SUPPORTED_IMAGE_EXTENSIONS

    def test_does_not_contain_video_extensions(self):
        assert ".mov" not in SUPPORTED_IMAGE_EXTENSIONS
        assert ".mp4" not in SUPPORTED_IMAGE_EXTENSIONS
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_utils.py::TestSupportedImageExtensions -v
```

Expected: `ImportError` or `AttributeError` — `SUPPORTED_IMAGE_EXTENSIONS` not defined yet.

- [ ] **Step 3: Add the constant to `utils.py`**

In `utils.py`, add after line 14 (`SUPPORTED_VIDEO_EXTENSIONS = {".mov", ".MOV"}`):

```python
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".heic", ".heif"}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_utils.py::TestSupportedImageExtensions -v
```

Expected: 2 PASSED.

- [ ] **Step 5: Commit**

```bash
git add utils.py tests/test_utils.py
git commit -m "feat: add SUPPORTED_IMAGE_EXTENSIONS constant to utils"
```

---

### Task 2: Fix `get_workspace_dir` to derive workspace from video path's parent

**Context:** `get_workspace_dir` currently returns `config.INPUT_DIR / video_path.stem`, hardcoding the workspace to `INPUT_DIR`. After cleanup, workspaces live in `COMPLETED_DIR`. Changing it to `video_path.parent / video_path.stem` makes the workspace relative to wherever the video lives — backward-compatible since existing callers always pass paths under `INPUT_DIR`.

**Files:**
- Modify: `utils.py:25`
- Test: `tests/test_utils.py` (existing `TestPathHelpers::test_get_workspace_dir`)

- [ ] **Step 1: Add a second assertion to the existing test that verifies the new behaviour**

In `tests/test_utils.py`, update `TestPathHelpers::test_get_workspace_dir`:

```python
def test_get_workspace_dir(self, patched_input, tmp_path):
    # Existing behaviour: video under INPUT_DIR → workspace under INPUT_DIR
    video = patched_input / "ms_LeovsKhanh.mov"
    assert get_workspace_dir(video) == patched_input / "ms_LeovsKhanh"

    # New behaviour: video under any directory → workspace under same directory
    other_dir = tmp_path / "completed"
    other_dir.mkdir()
    video2 = other_dir / "ms_LeovsKhanh.mov"
    assert get_workspace_dir(video2) == other_dir / "ms_LeovsKhanh"
```

- [ ] **Step 2: Run test to verify the second assertion fails**

```bash
uv run pytest tests/test_utils.py::TestPathHelpers::test_get_workspace_dir -v
```

Expected: FAIL — second assertion fails because `get_workspace_dir` still returns `INPUT_DIR / stem`.

- [ ] **Step 3: Fix `get_workspace_dir` in `utils.py`**

Change line 26 in `utils.py` from:

```python
def get_workspace_dir(video_path: Path) -> Path:
    return config.INPUT_DIR / video_path.stem
```

to:

```python
def get_workspace_dir(video_path: Path) -> Path:
    return video_path.parent / video_path.stem
```

- [ ] **Step 4: Run the full test suite to verify nothing regressed**

```bash
uv run pytest tests/test_utils.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add utils.py tests/test_utils.py
git commit -m "fix: derive workspace from video path parent instead of hardcoded INPUT_DIR"
```

---

### Task 3: Create `rethumbnail.py` with `find_manual_thumbnail`

**Files:**
- Create: `rethumbnail.py`
- Create: `tests/test_rethumbnail.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rethumbnail.py`:

```python
import time
from pathlib import Path

import pytest

from rethumbnail import find_manual_thumbnail


class TestFindManualThumbnail:
    def test_raises_when_no_images(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="No manual thumbnail"):
            find_manual_thumbnail(tmp_path)

    def test_returns_single_valid_image(self, tmp_path):
        img = tmp_path / "my_photo.jpg"
        img.write_bytes(b"fake")
        assert find_manual_thumbnail(tmp_path) == img

    def test_picks_most_recently_modified(self, tmp_path):
        older = tmp_path / "old.jpg"
        older.write_bytes(b"old")
        time.sleep(0.05)
        newer = tmp_path / "new.jpg"
        newer.write_bytes(b"new")
        assert find_manual_thumbnail(tmp_path) == newer

    def test_raises_when_only_reserved_names(self, tmp_path):
        (tmp_path / "selected.jpg").write_bytes(b"s")
        (tmp_path / "thumbnail.jpg").write_bytes(b"t")
        with pytest.raises(FileNotFoundError, match="No manual thumbnail"):
            find_manual_thumbnail(tmp_path)

    def test_ignores_reserved_names_returns_valid(self, tmp_path):
        (tmp_path / "selected.jpg").write_bytes(b"s")
        (tmp_path / "thumbnail.jpg").write_bytes(b"t")
        valid = tmp_path / "manual.png"
        valid.write_bytes(b"v")
        assert find_manual_thumbnail(tmp_path) == valid

    def test_accepts_all_supported_extensions(self, tmp_path):
        for ext in [".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif", ".gif", ".heic", ".heif"]:
            f = tmp_path / f"image{ext}"
            f.write_bytes(b"data")
        # All are valid; just verify it doesn't raise
        result = find_manual_thumbnail(tmp_path)
        assert result.exists()

    def test_ignores_non_image_files(self, tmp_path):
        (tmp_path / "notes.txt").write_bytes(b"text")
        (tmp_path / "data.json").write_bytes(b"{}")
        with pytest.raises(FileNotFoundError):
            find_manual_thumbnail(tmp_path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_rethumbnail.py -v
```

Expected: `ModuleNotFoundError` — `rethumbnail` not created yet.

- [ ] **Step 3: Create `rethumbnail.py` with `find_manual_thumbnail`**

Create `rethumbnail.py` at the project root:

```python
import shutil
from pathlib import Path

from auth_service import get_client
from thumbnail_enhancement.renderer import render_thumbnail
from uploader import save_upload_record, set_thumbnail
from utils import (
    RENDERED_THUMBNAIL_NAME,
    SELECTED_CANDIDATE_NAME,
    SUPPORTED_IMAGE_EXTENSIONS,
    get_uploaded_record,
)


def find_manual_thumbnail(workspace_dir: Path) -> Path:
    RESERVED = {SELECTED_CANDIDATE_NAME, RENDERED_THUMBNAIL_NAME}
    candidates = [
        f for f in workspace_dir.iterdir()
        if f.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS and f.name not in RESERVED
    ]
    if not candidates:
        raise FileNotFoundError(f"No manual thumbnail image found in workspace: {workspace_dir}")
    return max(candidates, key=lambda f: f.stat().st_mtime)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_rethumbnail.py -v
```

Expected: 7 PASSED.

- [ ] **Step 5: Commit**

```bash
git add rethumbnail.py tests/test_rethumbnail.py
git commit -m "feat: add find_manual_thumbnail to rethumbnail.py"
```

---

### Task 4: Add `rethumbnail_video` to `rethumbnail.py`

**Context:** `rethumbnail_video(workspace_dir)` constructs a synthetic video path `workspace_dir.parent / f"{workspace_dir.name}.mov"` so that the fixed `get_workspace_dir` resolves to `workspace_dir`. It bypasses `set_thumbnail_for_video` (which early-returns when `thumbnail_set=True`) and calls `set_thumbnail` + `save_upload_record` directly.

**Files:**
- Modify: `rethumbnail.py`
- Modify: `tests/test_rethumbnail.py`

- [ ] **Step 1: Write the failing integration tests**

Add to `tests/test_rethumbnail.py`:

```python
from unittest.mock import MagicMock, patch

from schemas import UploadedRecord
from utils import RENDERED_THUMBNAIL_NAME, SELECTED_CANDIDATE_NAME

from rethumbnail import rethumbnail_video

_RECORD = UploadedRecord(
    video_id="abc123",
    uploaded_at="2026-01-01T00:00:00",
    thumbnail_set=True,
    youtube_link="https://youtu.be/abc123",
)


class TestRethumbnailVideo:
    def _setup_workspace(self, tmp_path):
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()
        manual_img = workspace_dir / "manual.jpg"
        manual_img.write_bytes(b"manual-image-bytes")
        old_thumbnail = workspace_dir / RENDERED_THUMBNAIL_NAME
        old_thumbnail.write_bytes(b"old-thumbnail")
        return workspace_dir, manual_img

    def test_replaces_selected_jpg_with_manual_image(self, tmp_path):
        workspace_dir, manual_img = self._setup_workspace(tmp_path)

        with patch("rethumbnail.get_uploaded_record", return_value=_RECORD), \
             patch("rethumbnail.render_thumbnail", return_value=str(workspace_dir / RENDERED_THUMBNAIL_NAME)), \
             patch("rethumbnail.get_client", return_value=MagicMock()), \
             patch("rethumbnail.set_thumbnail"), \
             patch("rethumbnail.save_upload_record"):
            rethumbnail_video(workspace_dir)

        selected = workspace_dir / SELECTED_CANDIDATE_NAME
        assert selected.read_bytes() == b"manual-image-bytes"

    def test_deletes_old_thumbnail_before_render(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)
        render_call_order = []

        def fake_render(video_path, *args, **kwargs):
            thumbnail_path = workspace_dir / RENDERED_THUMBNAIL_NAME
            render_call_order.append(thumbnail_path.exists())
            return str(thumbnail_path)

        with patch("rethumbnail.get_uploaded_record", return_value=_RECORD), \
             patch("rethumbnail.render_thumbnail", side_effect=fake_render), \
             patch("rethumbnail.get_client", return_value=MagicMock()), \
             patch("rethumbnail.set_thumbnail"), \
             patch("rethumbnail.save_upload_record"):
            rethumbnail_video(workspace_dir)

        assert render_call_order == [False], "thumbnail.jpg must be deleted before render is called"

    def test_calls_set_thumbnail_with_correct_video_id(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)
        mock_youtube = MagicMock()

        with patch("rethumbnail.get_uploaded_record", return_value=_RECORD), \
             patch("rethumbnail.render_thumbnail", return_value=str(workspace_dir / RENDERED_THUMBNAIL_NAME)), \
             patch("rethumbnail.get_client", return_value=mock_youtube), \
             patch("rethumbnail.set_thumbnail") as mock_set, \
             patch("rethumbnail.save_upload_record"):
            rethumbnail_video(workspace_dir)

        mock_set.assert_called_once_with(
            mock_youtube,
            "abc123",
            workspace_dir / RENDERED_THUMBNAIL_NAME,
        )

    def test_saves_upload_record_with_thumbnail_set_true(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)

        with patch("rethumbnail.get_uploaded_record", return_value=_RECORD), \
             patch("rethumbnail.render_thumbnail", return_value=str(workspace_dir / RENDERED_THUMBNAIL_NAME)), \
             patch("rethumbnail.get_client", return_value=MagicMock()), \
             patch("rethumbnail.set_thumbnail"), \
             patch("rethumbnail.save_upload_record") as mock_save:
            rethumbnail_video(workspace_dir)

        _, kwargs = mock_save.call_args
        assert kwargs["thumbnail_set"] is True

    def test_raises_when_no_upload_record(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)

        with patch("rethumbnail.get_uploaded_record", return_value=None):
            with pytest.raises(RuntimeError, match="No upload record"):
                rethumbnail_video(workspace_dir)

    def test_raises_when_upload_record_missing_video_id(self, tmp_path):
        workspace_dir, _ = self._setup_workspace(tmp_path)
        record_no_id = UploadedRecord(
            video_id="",
            uploaded_at="2026-01-01T00:00:00",
            thumbnail_set=False,
            youtube_link="",
        )

        with patch("rethumbnail.get_uploaded_record", return_value=record_no_id):
            with pytest.raises(RuntimeError, match="No upload record"):
                rethumbnail_video(workspace_dir)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_rethumbnail.py::TestRethumbnailVideo -v
```

Expected: `ImportError` — `rethumbnail_video` not defined yet.

- [ ] **Step 3: Add `rethumbnail_video` to `rethumbnail.py`**

Append to `rethumbnail.py` (after `find_manual_thumbnail`):

```python
def rethumbnail_video(workspace_dir: Path) -> None:
    fake_video_path = workspace_dir.parent / f"{workspace_dir.name}.mov"

    upload_record = get_uploaded_record(fake_video_path)
    if not upload_record or not upload_record.video_id:
        raise RuntimeError(f"No upload record found for workspace: {workspace_dir.name}")

    manual_image = find_manual_thumbnail(workspace_dir)

    selected_path = workspace_dir / SELECTED_CANDIDATE_NAME
    shutil.copy2(str(manual_image), str(selected_path))

    thumbnail_path = workspace_dir / RENDERED_THUMBNAIL_NAME
    thumbnail_path.unlink(missing_ok=True)

    render_thumbnail(str(fake_video_path))

    youtube_client = get_client()
    set_thumbnail(youtube_client, upload_record.video_id, thumbnail_path)
    save_upload_record(fake_video_path, upload_record.video_id, thumbnail_set=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_rethumbnail.py -v
```

Expected: all 13 PASSED.

- [ ] **Step 5: Commit**

```bash
git add rethumbnail.py tests/test_rethumbnail.py
git commit -m "feat: add rethumbnail_video orchestration function"
```

---

### Task 5: Add `rethumbnail` subcommand to `main.py`

**Files:**
- Modify: `main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Read existing `tests/test_main.py` to understand the testing pattern**

```bash
cat tests/test_main.py
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_main.py`:

```python
import sys
from unittest.mock import patch
from pathlib import Path

import pytest
import config


class TestCmdRethumbnail:
    def test_calls_rethumbnail_video_with_resolved_workspace(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch("main.rethumbnail_video") as mock_fn:
            from main import cmd_rethumbnail
            args = type("args", (), {"workspace": "xd_match"})()
            cmd_rethumbnail(args)

        mock_fn.assert_called_once_with(workspace_dir)

    def test_accepts_absolute_path(self, tmp_path):
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch("main.rethumbnail_video") as mock_fn:
            from main import cmd_rethumbnail
            args = type("args", (), {"workspace": str(workspace_dir)})()
            cmd_rethumbnail(args)

        mock_fn.assert_called_once_with(workspace_dir)

    def test_exits_when_workspace_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)

        from main import cmd_rethumbnail
        args = type("args", (), {"workspace": "nonexistent"})()
        with pytest.raises(SystemExit) as exc:
            cmd_rethumbnail(args)
        assert exc.value.code != 0

    def test_exits_on_file_not_found_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch("main.rethumbnail_video", side_effect=FileNotFoundError("no image")):
            from main import cmd_rethumbnail
            args = type("args", (), {"workspace": "xd_match"})()
            with pytest.raises(SystemExit) as exc:
                cmd_rethumbnail(args)
            assert exc.value.code != 0

    def test_exits_on_runtime_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path)
        workspace_dir = tmp_path / "xd_match"
        workspace_dir.mkdir()

        with patch("main.rethumbnail_video", side_effect=RuntimeError("no upload record")):
            from main import cmd_rethumbnail
            args = type("args", (), {"workspace": "xd_match"})()
            with pytest.raises(SystemExit) as exc:
                cmd_rethumbnail(args)
            assert exc.value.code != 0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_main.py::TestCmdRethumbnail -v
```

Expected: `ImportError` or `AttributeError` — `cmd_rethumbnail` not defined yet.

- [ ] **Step 4: Add `cmd_rethumbnail` and the subparser to `main.py`**

Add the import at the top of `main.py`, after existing imports:

```python
from rethumbnail import rethumbnail_video
```

Add the function before `main()`:

```python
def cmd_rethumbnail(args):
    workspace_arg = args.workspace
    workspace_dir = Path(workspace_arg)
    if not workspace_dir.is_absolute():
        workspace_dir = config.COMPLETED_DIR / workspace_arg
    if not workspace_dir.exists() or not workspace_dir.is_dir():
        logger.error(f"Workspace not found: {workspace_dir}")
        sys.exit(1)
    try:
        rethumbnail_video(workspace_dir)
        logger.info(f"Thumbnail updated successfully for {workspace_dir.name}")
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except RuntimeError as e:
        logger.error(str(e))
        sys.exit(1)
```

Add the subparser registration inside `main()`, after the `parser_test_overlay` block and before `args = parser.parse_args()`:

```python
parser_rethumbnail = subparsers.add_parser(
    "rethumbnail",
    help="Re-render and re-set thumbnail for a completed video",
    description=(
        "Detects a manually dropped image in the completed workspace, "
        "re-renders it through the thumbnail template, and sets it on YouTube."
    ),
)
parser_rethumbnail.add_argument(
    "workspace",
    help="Workspace folder name (e.g. 'xd_Nhut JPzVyvsDungzPhong') or full path inside COMPLETED_DIR",
)
parser_rethumbnail.set_defaults(func=cmd_rethumbnail)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_main.py::TestCmdRethumbnail -v
```

Expected: 5 PASSED.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add main.py tests/test_main.py
git commit -m "feat: add rethumbnail CLI subcommand"
```
