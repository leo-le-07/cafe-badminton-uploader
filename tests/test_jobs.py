from types import SimpleNamespace

import pytest

import config
import media_probe
import uploader
import utils
from app import pipeline, store
from app.jobs import JobQueue
from app.models import Job, Match, Segment
from custom_exceptions import AuthRequiredError, QuotaExceededError

HOUR = 3600


class FakeClock:
    def __init__(self, now=1_000_000.0):
        self.now = now

    def __call__(self):
        return self.now


class FakePipeline:
    """Records (match_id, step) calls; raises whatever `fail` holds for a call."""

    def __init__(self):
        self.calls = []
        self.fail = {}
        self.during = None

    def __call__(self, job, step, progress):
        self.calls.append((job.match.id, step))
        if self.during:
            self.during(job, step, progress)
        error = self.fail.get((job.match.id, step))
        if error is not None:
            raise error
        if step == "upload":
            vp = utils.workspace_video_path(store.workspace_dir(job.match.id))
            uploader.save_upload_record(vp, f"vid-{job.match.id}", thumbnail_set=False)

    def steps_of(self, match_id):
        return [step for id, step in self.calls if id == match_id]


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    monkeypatch.setattr(config, "QUOTA_RETRY_HOURS", 4)
    (tmp_path / "input").mkdir()
    probed = []

    def fake_probe(path):
        probed.append(path)
        return SimpleNamespace(recorded_at="2026-11-19T21:30:00+07:00")

    monkeypatch.setattr(media_probe, "probe", fake_probe)
    return probed


@pytest.fixture
def fake(monkeypatch):
    f = FakePipeline()
    monkeypatch.setattr(pipeline, "run_step", f)
    return f


@pytest.fixture
def clock():
    return FakeClock()


def _match(id, first_source="a.mov"):
    return Match(
        id=id,
        match_type="md",
        team1=["Nam", "Hùng"],
        team2=["Tú", "Long"],
        tournament="Cafe Game",
        segments=[Segment(first_source, 1.0, 20.0), Segment("b.mov", 0.0, 5.0)],
    )


def _drain(queue, limit=100):
    for _ in range(limit):
        if not queue.run_once():
            return
    raise AssertionError("queue never became idle")


def _status(queue, match_id):
    return next(j for j in queue.snapshot() if j["match"]["id"] == match_id)


def test_enqueue_creates_queued_job_with_recorded_date_of_first_source(
    dirs, fake, clock
):
    queue = JobQueue(clock=clock)
    match = _match("m1", first_source="first.mov")

    [job] = queue.enqueue([match])

    assert dirs == [config.INPUT_DIR / "first.mov"]
    assert job.recorded_date == "2026-11-19"
    assert (job.status, job.step, job.progress) == ("queued", "metadata", 0.0)
    assert store.load_job("m1").to_dict() == job.to_dict()
    match.team1.append("changed later")
    assert queue.snapshot()[0]["match"]["team1"] == ["Nam", "Hùng"]


def test_job_runs_all_steps_in_order_then_done(fake, clock):
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])

    _drain(queue)

    assert fake.steps_of("m1") == pipeline.STEPS
    job = _status(queue, "m1")
    assert job["status"] == "done"
    assert job["progress"] == 100
    assert job["error"] is None
    assert job["youtube_link"] == "https://youtu.be/vid-m1"


def test_run_once_does_one_step_and_returns_false_when_idle(fake, clock):
    queue = JobQueue(clock=clock)
    assert queue.run_once() is False
    queue.enqueue([_match("m1")])

    assert queue.run_once() is True
    assert fake.calls == [("m1", "metadata")]
    assert _status(queue, "m1")["step"] == "select_thumbnail"


def test_jobs_run_one_at_a_time_in_queue_order(fake, clock):
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])
    queue.enqueue([_match("m3")])

    _drain(queue)

    expected = [(id, step) for id in ("m1", "m2", "m3") for step in pipeline.STEPS]
    assert fake.calls == expected


def test_progress_and_step_are_persisted_to_job_json(fake, clock):
    seen = []

    def during(job, step, progress):
        if step != "encode":
            return
        progress(12.0)
        progress(42.4)
        progress(42.9)  # same integer percentage: not written again
        on_disk = store.load_job(job.match.id)
        seen.append((on_disk.status, on_disk.step, on_disk.progress))

    fake.during = during
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])

    _drain(queue)

    assert seen == [("running", "encode", 42.0)]


def test_progress_writes_are_throttled(fake, clock, monkeypatch):
    writes = []
    real_save = store.save_job

    def counting_save(job):
        writes.append(job.progress)
        real_save(job)

    def during(job, step, progress):
        if step == "encode":
            for i in range(1000):
                progress(i / 100)  # 0.00 .. 9.99 -> integers 0..9

    fake.during = during
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])
    for _ in range(3):  # metadata, select_thumbnail, render_thumbnail
        queue.run_once()

    monkeypatch.setattr(store, "save_job", counting_save)
    queue.run_once()  # encode

    assert writes.count(5.0) == 1
    assert len(writes) < 15


def test_error_stops_that_job_and_queue_moves_on(fake, clock):
    fake.fail[("m1", "encode")] = RuntimeError("ffmpeg exploded")
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])

    _drain(queue)

    job1 = _status(queue, "m1")
    assert job1["status"] == "error"
    assert job1["step"] == "encode"
    assert "ffmpeg exploded" in job1["error"]
    assert job1["error"].startswith("encode")
    assert fake.steps_of("m1")[-1] == "encode"
    assert _status(queue, "m2")["status"] == "done"
    assert store.load_job("m1").status == "error"


def test_retry_resumes_from_failed_step_not_from_start(fake, clock):
    fake.fail[("m1", "encode")] = RuntimeError("boom")
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])
    _drain(queue)
    fake.calls.clear()
    del fake.fail[("m1", "encode")]

    queue.retry("m1")
    assert _status(queue, "m1")["status"] == "queued"
    assert _status(queue, "m1")["error"] is None
    _drain(queue)

    assert fake.steps_of("m1") == pipeline.STEPS[pipeline.STEPS.index("encode") :]
    assert _status(queue, "m1")["status"] == "done"


def test_retry_refused_for_jobs_that_did_not_stop(fake, clock):
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])
    with pytest.raises(ValueError):
        queue.retry("m1")
    with pytest.raises(KeyError):
        queue.retry("unknown")


def test_quota_puts_job_in_waiting_and_blocks_later_uploads_only(fake, clock):
    fake.fail[("m1", "upload")] = QuotaExceededError("quota")
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])

    _drain(queue)

    job1 = _status(queue, "m1")
    assert job1["status"] == "waiting_quota"
    assert job1["step"] == "upload"
    assert job1["error"] == "Chờ quota YouTube, sẽ tự thử lại"
    job2 = _status(queue, "m2")
    assert job2["status"] == "waiting_quota"
    assert job2["step"] == "upload"
    assert fake.steps_of("m2") == ["metadata", "select_thumbnail", "render_thumbnail", "encode"]
    assert fake.steps_of("m1").count("upload") == 1


def test_waiting_quota_retries_after_configured_hours(fake, clock):
    fake.fail[("m1", "upload")] = QuotaExceededError("quota")
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])
    _drain(queue)
    fake.calls.clear()

    clock.now += 4 * HOUR - 1
    assert queue.run_once() is False
    assert fake.calls == []

    clock.now += 1
    del fake.fail[("m1", "upload")]
    _drain(queue)

    assert fake.calls[0] == ("m1", "upload")
    assert _status(queue, "m1")["status"] == "done"
    assert _status(queue, "m2")["status"] == "done"


def test_quota_again_on_retry_keeps_later_jobs_waiting(fake, clock):
    fake.fail[("m1", "upload")] = QuotaExceededError("quota")
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])
    _drain(queue)
    fake.calls.clear()

    clock.now += 4 * HOUR
    _drain(queue)

    assert fake.calls == [("m1", "upload")]
    assert _status(queue, "m2")["status"] == "waiting_quota"


def test_manual_retry_of_quota_job_tries_upload_now(fake, clock):
    fake.fail[("m1", "upload")] = QuotaExceededError("quota")
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])
    _drain(queue)
    fake.calls.clear()
    del fake.fail[("m1", "upload")]

    queue.retry("m2")
    _drain(queue)

    assert ("m1", "upload") in fake.calls
    assert ("m2", "upload") in fake.calls
    assert _status(queue, "m1")["status"] == "done"
    assert _status(queue, "m2")["status"] == "done"


def test_auth_error_marks_job_error_and_worker_survives(fake, clock):
    fake.fail[("m1", "upload")] = AuthRequiredError("token expired")
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])
    _drain(queue)

    job1 = _status(queue, "m1")
    assert job1["status"] == "error"
    assert "đăng nhập" in job1["error"]

    queue.enqueue([_match("m2")])
    assert queue.run_once() is True
    assert fake.calls[-1] == ("m2", "metadata")


def test_unexpected_exception_in_bookkeeping_does_not_leave_job_executing(
    fake, clock, monkeypatch
):
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])
    real_save = store.save_job
    failing = {"on": True}

    def flaky_save(job):
        if failing["on"] and job.step == "select_thumbnail":
            raise OSError("disk full")
        real_save(job)

    monkeypatch.setattr(store, "save_job", flaky_save)
    with pytest.raises(OSError):
        queue.run_once()
    failing["on"] = False

    # Not stuck as "executing": it can still be unqueued.
    assert queue.unqueue("m1").id == "m1"


def _write_job(id, status, step, queued_at):
    store.save_job(
        Job(
            match=_match(id),
            recorded_date="2026-11-19",
            status=status,
            step=step,
            progress=37.0,
            error="Chờ quota YouTube, sẽ tự thử lại" if status == "waiting_quota" else None,
            youtube_link=None,
            queued_at=queued_at,
        )
    )


def test_restart_resumes_unfinished_jobs(fake, clock):
    _write_job("m1", "waiting_quota", "upload", "2026-11-20T10:00:00")
    _write_job("m2", "running", "encode", "2026-11-20T10:00:01")

    queue = JobQueue(clock=clock)
    assert queue.locked_match_ids() == {"m1", "m2"}
    assert queue.run_once() is True
    assert fake.calls == [("m1", "upload")]  # quota wait is not remembered

    _drain(queue)

    assert fake.steps_of("m2") == pipeline.STEPS[pipeline.STEPS.index("encode") :]
    assert _status(queue, "m1")["status"] == "done"
    assert _status(queue, "m2")["status"] == "done"


def test_restart_does_not_rerun_finished_or_failed_jobs(fake, clock):
    _write_job("m1", "error", "encode", "2026-11-20T10:00:00")

    queue = JobQueue(clock=clock)

    assert queue.run_once() is False
    assert _status(queue, "m1")["status"] == "error"


def test_unqueue_removes_workspace_and_returns_match(fake, clock):
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])
    queue.run_once()  # m1 metadata

    match = queue.unqueue("m1")

    assert match == _match("m1")
    assert not store.workspace_dir("m1").exists()
    assert queue.locked_match_ids() == {"m2"}
    assert [j["match"]["id"] for j in queue.snapshot()] == ["m2"]
    _drain(queue)
    assert fake.steps_of("m1") == ["metadata"]


def test_unqueue_refused_when_running_or_uploaded(fake, clock):
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1"), _match("m2")])
    refused = []

    def during(job, step, progress):
        if job.match.id == "m1" and step == "encode":
            with pytest.raises(ValueError):
                queue.unqueue("m1")
            refused.append(step)

    fake.during = during
    fake.fail[("m1", "set_thumbnail")] = RuntimeError("thumbnail rejected")
    _drain(queue)

    assert refused == ["encode"]
    assert _status(queue, "m1")["status"] == "error"  # uploaded, then failed
    with pytest.raises(ValueError):
        queue.unqueue("m1")
    assert store.workspace_dir("m1").exists()
    with pytest.raises(ValueError):
        queue.unqueue("m2")  # done
    with pytest.raises(KeyError):
        queue.unqueue("unknown")


def test_enqueue_rejects_match_with_problems_or_already_queued(fake, clock):
    queue = JobQueue(clock=clock)
    queue.enqueue([_match("m1")])
    incomplete = _match("m2")
    incomplete.team2 = [""]

    with pytest.raises(ValueError):
        queue.enqueue([incomplete])
    with pytest.raises(ValueError):
        queue.enqueue([_match("m3"), _match("m1")])
    with pytest.raises(ValueError):
        queue.enqueue([_match("m4"), _match("m4")])

    assert queue.locked_match_ids() == {"m1"}
    assert not store.workspace_dir("m3").exists()


def test_queue_order_survives_restart_for_jobs_enqueued_together(fake, clock):
    queue = JobQueue(clock=clock)
    ids = [f"m{i}" for i in range(10)]
    queue.enqueue([_match(id) for id in ids])

    restarted = JobQueue(clock=clock)

    assert [j["match"]["id"] for j in restarted.snapshot()] == ids


def test_start_and_stop_do_not_hang(fake):
    queue = JobQueue()
    queue.enqueue([_match("m1")])
    queue.start()
    queue.stop()
