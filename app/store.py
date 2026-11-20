"""JSON persistence for the editor session, job state and player-name history.

Every write goes to a temp file in the same directory and is then moved into
place with os.replace, so a crash never leaves a half-written file behind.
"""

import json
import os
import shutil
import tempfile
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar

import config
from app.models import Job, Session
from logger import get_logger
from utils import METADATA_FILE

logger = get_logger(__name__)

SESSION_FILE = "session.json"
PLAYERS_FILE = "players.json"
JOB_FILE = "job.json"
WORKSPACES_DIR = "workspaces"

_players_lock = threading.Lock()

T = TypeVar("T")


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=path.parent, prefix=f"{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


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
