"""JSON persistence for the editor session, job state and player-name history.

Every write goes to a temp file in the same directory and is then moved into
place with os.replace, so a crash never leaves a half-written file behind.
"""

import json
import os
import re
import shutil
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

import config
from app.models import Job, Session
from logger import get_logger
from utils import METADATA_FILE, UPLOADED_FILE, write_json_atomic

logger = get_logger(__name__)

SESSION_FILE = "session.json"
PLAYERS_FILE = "players.json"
JOB_FILE = "job.json"
MODE_FILE = "mode.json"
WORKSPACES_DIR = "workspaces"

_players_lock = threading.Lock()

T = TypeVar("T")


def _write_json(path: Path, data) -> None:
    write_json_atomic(path, data)


def _read_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load(path: Path, parse: Callable[[Any], T]) -> T | None:
    """Read and parse a JSON file; None if it is missing or unusable.

    An unusable file (invalid JSON or wrong shape) is renamed to
    `<name>.corrupt-<timestamp>` next to it, never deleted.
    """
    if not path.exists():
        return None
    try:
        return parse(_read_json(path))
    except (ValueError, KeyError, TypeError) as e:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        kept = path.with_name(f"{path.name}.corrupt-{stamp}")
        os.replace(path, kept)
        logger.warning(f"{path} is corrupt ({e}); kept as {kept.name}")
        return None


def load_session() -> Session:
    session = _load(config.DATA_DIR / SESSION_FILE, Session.from_dict)
    return session if session is not None else Session([], [], None)


def save_session(s: Session) -> None:
    _write_json(config.DATA_DIR / SESSION_FILE, s.to_dict())


def _parse_mode(data) -> str:
    mode = data.get("mode") if isinstance(data, dict) else None
    if not isinstance(mode, str) or mode not in config.MODES:
        raise ValueError(f"unknown mode: {mode!r}")
    return mode


def load_mode() -> str:
    """The mode last chosen in the editor; "dev" if none is stored or usable."""
    return _load(config.DATA_DIR / MODE_FILE, _parse_mode) or config.DEFAULT_MODE


def save_mode(mode: str) -> None:
    _write_json(config.DATA_DIR / MODE_FILE, {"mode": _parse_mode({"mode": mode})})


def workspace_dir(match_id: str) -> Path:
    return config.DATA_DIR / WORKSPACES_DIR / match_id


def load_job(match_id: str) -> Job | None:
    return _load(workspace_dir(match_id) / JOB_FILE, Job.from_dict)


def save_job(job: Job) -> None:
    _write_json(workspace_dir(job.match.id) / JOB_FILE, job.to_dict())


def list_jobs() -> list[Job]:
    root = config.DATA_DIR / WORKSPACES_DIR
    if not root.exists():
        return []
    jobs = [_load(path, Job.from_dict) for path in root.glob(f"*/{JOB_FILE}")]
    return sorted((job for job in jobs if job), key=lambda job: job.queued_at)


def list_archived_jobs() -> list[Job]:
    """Finished jobs archived in COMPLETED_DIR, sorted by queued_at.

    Read-only: COMPLETED_DIR also holds workspaces from before job.json
    existed and files the user put there, so a missing or unreadable job.json
    is skipped and nothing is ever renamed.
    """
    root = config.COMPLETED_DIR
    if not root.exists():
        return []
    jobs = []
    for path in root.glob(f"*/{JOB_FILE}"):
        try:
            job = Job.from_dict(_read_json(path))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
        if job.status == "done":
            jobs.append(job)
    return sorted(jobs, key=lambda job: job.queued_at)


_ARCHIVE_NAME = re.compile(r"\d{4}-\d{2}-\d{2}_(?P<id>[a-z0-9-]+)")
_COLLISION_SUFFIX = re.compile(r"-\d+$")


def archived_upload_ids() -> set[str]:
    """Match ids of archives in COMPLETED_DIR whose upload.json holds a video id.

    The id comes from the archive's job.json when it is readable, otherwise
    from the folder name `<recorded_date>_<match_id>`. cleanup adds `-<n>` to
    the name on a collision, and a match id can itself end in `-<digits>`, so
    both readings of such a name are returned; an id that matches no match
    is harmless. Read-only: nothing in COMPLETED_DIR is changed.
    """
    root = config.COMPLETED_DIR
    if not root.exists():
        return set()
    ids: set[str] = set()
    for folder in root.iterdir():
        record = folder / UPLOADED_FILE
        if not record.is_file():
            continue
        try:
            data = _read_json(record)
            if not (isinstance(data, dict) and data.get("video_id")):
                continue
        except (OSError, ValueError):
            continue
        try:
            ids.add(Job.from_dict(_read_json(folder / JOB_FILE)).match.id)
            continue
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            pass
        named = _ARCHIVE_NAME.fullmatch(folder.name)
        if named:
            ids.add(named["id"])
            ids.add(_COLLISION_SUFFIX.sub("", named["id"]))
    return ids


def delete_workspace(match_id: str) -> None:
    shutil.rmtree(workspace_dir(match_id), ignore_errors=True)


def _players_path() -> Path:
    return config.DATA_DIR / PLAYERS_FILE


def _parse_players(data) -> dict[str, int]:
    if not isinstance(data, dict) or not all(
        isinstance(name, str) and type(count) is int for name, count in data.items()
    ):
        raise TypeError("expected an object mapping names to counts")
    return data


def load_players() -> dict[str, int]:
    return _load(_players_path(), _parse_players) or {}


def record_players(names: list[str]) -> None:
    with _players_lock:
        counts = Counter(load_players())
        counts.update(name.strip() for name in names if name.strip())
        _write_json(_players_path(), dict(counts))


def seed_players_from_completed() -> None:
    """Build the initial name history from past uploads; runs only once."""
    with _players_lock:
        if _players_path().exists():
            return
        counts: Counter[str] = Counter()
        for path in sorted(config.COMPLETED_DIR.glob(f"*/{METADATA_FILE}")):
            try:
                metadata = _read_json(path)
                names = metadata["team1_names"] + metadata["team2_names"]
            except (ValueError, KeyError, TypeError) as e:
                logger.warning(f"Skipping unreadable {path}: {e}")
                continue
            counts.update(name.strip() for name in names if name.strip())
        _write_json(_players_path(), dict(counts))
