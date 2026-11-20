"""The steps that turn one queued match into an archived YouTube upload.

Each step skips itself when its result is already on disk, so a step can be
re-run after a crash or a retry without redoing work or uploading twice.
"""

from dataclasses import replace
from pathlib import Path
from typing import Callable

import cleanup
import config
import uploader
import utils
import video_overlay
import video_prep
from app import store
from app.models import JOB_STEPS, Job, title_fields
from custom_exceptions import VideoAlreadyUploadedError
from logger import get_logger
from schemas import UploadedRecord
from thumbnail_enhancement import render_thumbnail

logger = get_logger(__name__)

STEPS: list[str] = list(JOB_STEPS)

Progress = Callable[[float], None]


def _video_path(match_id: str) -> Path:
    return utils.workspace_video_path(store.workspace_dir(match_id))


def uploaded_record(match_id: str) -> UploadedRecord | None:
    """The match's upload record, only if it holds a YouTube video id."""
    record = utils.get_uploaded_record(_video_path(match_id))
    return record if record and record.video_id else None


def has_upload_session(match_id: str) -> bool:
    """Whether a resumable upload was started and not finished: the video may
    already be complete on YouTube with the final response lost."""
    return uploader.get_upload_session_path(_video_path(match_id)).exists()


def needs_youtube(match_id: str, step: str) -> bool:
    """Whether running `step` now would call the YouTube API."""
    record = uploaded_record(match_id)
    if step == "upload":
        return record is None
    if step == "set_thumbnail":
        return record is None or not record.thumbnail_set
    return False


def _metadata(job: Job, vp: Path, progress: Progress) -> None:
    path = utils.get_metadata_path(vp)
    if path.exists():
        return
    names1, names2, tournament = title_fields(job.match)
    metadata = video_prep.create_metadata_from_fields(
        job.match.match_type, names1, names2, tournament, job.recorded_date
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    video_prep.store(vp, metadata)


def _select_thumbnail(job: Job, vp: Path, progress: Progress) -> None:
    output = utils.get_selected_candidate_path(vp)
    if output.exists():
        return
    video_prep.select_thumbnail_from_segments(
        job.match.segments, config.INPUT_DIR, output
    )


def _render_thumbnail(job: Job, vp: Path, progress: Progress) -> None:
    if utils.get_thumbnail_path(vp).exists():
        return
    render_thumbnail(str(vp))


def _encode(job: Job, vp: Path, progress: Progress) -> None:
    output = utils.get_processed_video_path(vp)
    if output.exists():
        return
    video_overlay.render_match(job.match.segments, config.INPUT_DIR, output, progress)


def _upload(job: Job, vp: Path, progress: Progress) -> None:
    if uploaded_record(job.match.id):
        return
    processed = utils.get_processed_video_path(vp)
    if not processed.exists():
        # Without this the uploader would fall back to uploading `vp`, which
        # is not a real file for a workspace.
        raise FileNotFoundError(f"Encoded video missing: {processed}")
    try:
        uploader.upload_video_with_idempotency(
            str(vp), progress, privacy_status=config.MODES[job.mode]
        )
    except VideoAlreadyUploadedError:
        logger.info(f"{job.match.id} was already uploaded")


def _set_thumbnail(job: Job, vp: Path, progress: Progress) -> None:
    uploader.set_thumbnail_for_video(str(vp))


def _cleanup(job: Job, vp: Path, progress: Progress) -> None:
    record = uploaded_record(job.match.id)
    if record is None:
        raise RuntimeError("Cannot archive a match that has not been uploaded")
    # The archived job.json is the job's final state; the queue does not
    # write job.json again after this step.
    done = replace(
        job,
        status="done",
        progress=100.0,
        error=None,
        youtube_link=record.youtube_link,
    )
    store.save_job(done)
    cleanup.archive_workspace(job.match.id)
    # The workspace is gone now, so this step must not fail after this point.
    try:
        store.record_players(job.match.team1 + job.match.team2)
    except Exception as e:
        logger.warning(f"Could not record player names of {job.match.id}: {e}")


_HANDLERS: dict[str, Callable[[Job, Path, Progress], None]] = {
    "metadata": _metadata,
    "select_thumbnail": _select_thumbnail,
    "render_thumbnail": _render_thumbnail,
    "encode": _encode,
    "upload": _upload,
    "set_thumbnail": _set_thumbnail,
    "cleanup": _cleanup,
}


def run_step(job: Job, step: str, progress: Progress) -> None:
    handler = _HANDLERS.get(step)
    if handler is None:
        raise ValueError(f"Unknown step: {step}")
    handler(job, _video_path(job.match.id), progress)
