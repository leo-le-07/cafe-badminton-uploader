"""Background queue that runs the per-match pipeline one step at a time.

Locking: `self._lock` guards `_jobs`, `_executing` and `_quota_until`, and every
`store.save_job` call (so the worker and API threads never write the same
job.json at once). Pipeline steps run outside the lock; while a step runs,
`_executing` names its match so `unqueue` can refuse it.
"""

import threading
import time
from datetime import datetime, timedelta
from typing import Callable

import config
import media_probe
from app import pipeline, store
from app.models import Job, Match, match_problems
from custom_exceptions import AuthRequiredError, QuotaExceededError
from logger import get_logger

logger = get_logger(__name__)

QUOTA_MESSAGE = "Chờ quota YouTube, sẽ tự thử lại"
AUTH_MESSAGE = (
    "Chưa đăng nhập YouTube hoặc phiên đăng nhập đã hết hạn. "
    "Hãy đăng nhập lại rồi bấm Thử lại."
)
IDLE_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 5.0


def _copy(job: Job) -> Job:
    return Job.from_dict(job.to_dict())


class JobQueue:
    def __init__(self, clock: Callable[[], float] = time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}  # in queue order
        self._executing: str | None = None
        # Retry time of each waiting_quota job; kept in memory only, so every
        # waiting job is retried right away after a restart.
        self._quota_until: dict[str, float] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        for job in store.list_jobs():
            if job.status == "done":
                # Only an interrupted cleanup leaves a done job outside
                # COMPLETED_DIR: finish archiving it.
                job.status = "queued"
                job.step = "cleanup"
            self._jobs[job.match.id] = job

    # ---- API-side operations -------------------------------------------------

    def enqueue(self, matches: list[Match]) -> list[Job]:
        ids = [match.id for match in matches]
        if len(set(ids)) != len(ids):
            raise ValueError("Một trận được đưa vào hàng đợi hai lần")
        for match in matches:
            problems = match_problems(match)
            if problems:
                raise ValueError(f"Trận {match.id}: {'; '.join(problems)}")

        # Probing runs ffprobe, so it stays outside the lock.
        recorded_dates = [
            media_probe.probe(config.INPUT_DIR / match.segments[0].source)
            .recorded_at[:10]
            for match in matches
        ]

        with self._lock:
            for id in ids:
                if id in self._jobs:
                    raise ValueError(f"Trận {id} đã có trong hàng đợi")
            jobs = []
            for match, recorded_date in zip(matches, recorded_dates):
                job = Job(
                    match=Match.from_dict(match.to_dict()),
                    recorded_date=recorded_date,
                    status="queued",
                    step=pipeline.STEPS[0],
                    progress=0.0,
                    error=None,
                    youtube_link=None,
                    queued_at=self._next_queued_at(),
                )
                store.save_job(job)
                self._jobs[job.match.id] = job
                jobs.append(_copy(job))
            return jobs

    def retry(self, match_id: str) -> None:
        with self._lock:
            job = self._jobs[match_id]
            if job.status not in ("error", "waiting_quota"):
                raise ValueError(f"Trận {match_id} không ở trạng thái lỗi hay chờ quota")
            if job.status == "waiting_quota":
                # The user says quota is back: let every waiting job try again.
                self._quota_until.clear()
            job.status = "queued"
            job.error = None
            store.save_job(job)

    def unqueue(self, match_id: str) -> Match:
        with self._lock:
            job = self._jobs[match_id]
            if self._executing == match_id:
                raise ValueError(f"Trận {match_id} đang được xử lý")
            if job.status == "done" or pipeline.uploaded_record(match_id):
                raise ValueError(f"Trận {match_id} đã upload lên YouTube")
            del self._jobs[match_id]
            self._quota_until.pop(match_id, None)
            store.delete_workspace(match_id)
            return job.match

    def snapshot(self) -> list[dict]:
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def locked_match_ids(self) -> set[str]:
        with self._lock:
            return set(self._jobs)

    # ---- worker --------------------------------------------------------------

    def run_once(self) -> bool:
        """Run at most one step of one job; False when nothing can run now."""
        with self._lock:
            now = self._clock()
            job = self._next_runnable(now)
            if job is None:
                return False
            match_id, step = job.match.id, job.step

            if step == "upload" and not pipeline.uploaded_record(match_id):
                blocked_until = self._quota_blocked_until(match_id, now)
                if blocked_until is not None:
                    # Another job hit the quota: wait with it instead of
                    # calling the uploader.
                    self._wait_for_quota(job, blocked_until)
                    return True

            job.status = "running"
            job.error = None
            job.progress = 0.0
            store.save_job(job)
            self._executing = match_id
            work = _copy(job)

        error: Exception | None = None
        try:
            pipeline.run_step(work, step, lambda p: self._report_progress(match_id, p))
        except Exception as e:
            error = e
        except BaseException:
            with self._lock:
                self._executing = None
            raise
        with self._lock:
            self._executing = None
            self._finish_step(self._jobs[match_id], step, error)
        return True

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="job-queue", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the worker loop; a step already running is left to finish (or
        to be resumed on next start) if it takes longer than the timeout."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=STOP_TIMEOUT_SECONDS)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:
                logger.exception("Job queue step failed")
                worked = False
            if not worked:
                self._stop.wait(IDLE_SECONDS)

    # ---- helpers (caller holds the lock) --------------------------------------

    def _next_runnable(self, now: float) -> Job | None:
        for job in self._jobs.values():
            if job.status in ("queued", "running"):
                return job
            if job.status == "waiting_quota" and (
                self._quota_until.get(job.match.id, now) <= now
            ):
                return job
        return None

    def _quota_blocked_until(self, match_id: str, now: float) -> float | None:
        waits = [
            until
            for id, until in self._quota_until.items()
            if id != match_id and until > now
        ]
        return max(waits) if waits else None

    def _wait_for_quota(self, job: Job, until: float) -> None:
        job.status = "waiting_quota"
        job.error = QUOTA_MESSAGE
        job.progress = 0.0
        self._quota_until[job.match.id] = until
        store.save_job(job)

    def _finish_step(self, job: Job, step: str, error: Exception | None) -> None:
        if isinstance(error, QuotaExceededError):
            until = self._clock() + config.QUOTA_RETRY_HOURS * 3600
            self._wait_for_quota(job, until)
            return
        self._quota_until.pop(job.match.id, None)
        if error is not None:
            if isinstance(error, AuthRequiredError):
                job.error = AUTH_MESSAGE
            else:
                logger.error(f"{job.match.id}: step {step} failed: {error!r}")
                job.error = f"{step}: {str(error) or type(error).__name__}"
            job.status = "error"
            store.save_job(job)
            return

        if step == "upload":
            record = pipeline.uploaded_record(job.match.id)
            job.youtube_link = record.youtube_link if record else None
        index = pipeline.STEPS.index(step)
        if index == len(pipeline.STEPS) - 1:
            # The cleanup step already wrote the final job.json into the
            # archive; writing it here would recreate the workspace.
            job.status = "done"
            job.progress = 100.0
            job.error = None
            return
        job.step = pipeline.STEPS[index + 1]
        job.progress = 0.0
        store.save_job(job)

    def _report_progress(self, match_id: str, percent: float) -> None:
        value = float(int(max(0.0, min(100.0, percent))))
        with self._lock:
            job = self._jobs.get(match_id)
            if job is None or self._executing != match_id or job.progress == value:
                return
            job.progress = value
            store.save_job(job)

    def _next_queued_at(self) -> str:
        """Now as ISO 8601, strictly after every queued job so the order
        survives a restart (list_jobs sorts by queued_at)."""
        stamp = datetime.now()
        latest = max(
            (datetime.fromisoformat(job.queued_at) for job in self._jobs.values()),
            default=None,
        )
        if latest is not None and stamp <= latest:
            stamp = latest + timedelta(microseconds=1)
        return stamp.isoformat()
