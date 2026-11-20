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


def load_session() -> Session:
    path = config.DATA_DIR / SESSION_FILE
    if not path.exists():
        return Session([], [], None)
    try:
        return Session.from_dict(_read_json(path))
    except (ValueError, KeyError, TypeError) as e:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        kept = path.with_name(f"{SESSION_FILE}.corrupt-{stamp}")
        os.replace(path, kept)
        logger.error(f"Session file is corrupt ({e}); kept as {kept.name}")
        return Session([], [], None)


def save_session(s: Session) -> None:
    _write_json(config.DATA_DIR / SESSION_FILE, s.to_dict())


def workspace_dir(match_id: str) -> Path:
    return config.DATA_DIR / WORKSPACES_DIR / match_id


def load_job(match_id: str) -> Job | None:
    path = workspace_dir(match_id) / JOB_FILE
    if not path.exists():
        return None
    return Job.from_dict(_read_json(path))


def save_job(job: Job) -> None:
    _write_json(workspace_dir(job.match.id) / JOB_FILE, job.to_dict())


def list_jobs() -> list[Job]:
    root = config.DATA_DIR / WORKSPACES_DIR
    if not root.exists():
        return []
    jobs = [Job.from_dict(_read_json(path)) for path in root.glob(f"*/{JOB_FILE}")]
    return sorted(jobs, key=lambda job: job.queued_at)


def delete_workspace(match_id: str) -> None:
    shutil.rmtree(workspace_dir(match_id), ignore_errors=True)


def _players_path() -> Path:
    return config.DATA_DIR / PLAYERS_FILE


def load_players() -> dict[str, int]:
    path = _players_path()
    if not path.exists():
        return {}
    return dict(_read_json(path))


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
