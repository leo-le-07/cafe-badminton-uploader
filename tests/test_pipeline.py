import json

import pytest

import config
import uploader
import utils
import video_overlay
import video_prep
from app import pipeline, store
from app.models import Job, Match, Segment
from app.pipeline import STEPS, run_step
from custom_exceptions import VideoAlreadyUploadedError
from rethumbnail import scan_completed_workspaces


def noop(_percent):
    pass


def _job():
    return Job(
        match=Match(
            id="m1",
            match_type="md",
            team1=["Nam", "Hùng"],
            team2=["Tú", "Long"],
            tournament="Cafe Game",
            segments=[Segment("a.mov", 1.5, 30.0), Segment("b.mov", 0.0, 12.0)],
        ),
        recorded_date="2026-11-19",
        status="running",
        step="metadata",
        progress=0.0,
        error=None,
        youtube_link=None,
        queued_at="2026-11-20T10:00:00",
    )


class Calls:
    def __init__(self):
        self.names = []

    def record(self, name, result=None, write=None):
        def fake(*args, **kwargs):
            self.names.append(name)
            if write is not None:
                write.write_bytes(b"x")
            return result

        return fake


@pytest.fixture
def job():
    return _job()


@pytest.fixture
def ws(tmp_path, monkeypatch, job):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    (tmp_path / "input").mkdir()
    (tmp_path / "completed").mkdir()
    store.save_job(job)
    return store.workspace_dir(job.match.id)


@pytest.fixture
def calls(monkeypatch, ws):
    """Replace every heavy or networked function the pipeline calls."""
    vp = utils.workspace_video_path(ws)
    c = Calls()

    def fake_upload(video_path, heartbeat_callback=None):
        c.names.append("upload")
        uploader.save_upload_record(vp, "vid1", thumbnail_set=False)
        return utils.get_uploaded_record(vp)

    monkeypatch.setattr(
        video_prep,
        "select_thumbnail_from_segments",
        c.record("select", write=utils.get_selected_candidate_path(vp)),
    )
    monkeypatch.setattr(
        pipeline,
        "render_thumbnail",
        c.record("render", write=utils.get_thumbnail_path(vp)),
    )
    monkeypatch.setattr(
        video_overlay,
        "render_match",
        c.record("encode", write=utils.get_processed_video_path(vp)),
    )
    monkeypatch.setattr(uploader, "upload_video_with_idempotency", fake_upload)
    monkeypatch.setattr(uploader, "set_thumbnail_for_video", c.record("set_thumb"))
    return c


def test_steps_are_in_pipeline_order():
    assert STEPS == [
        "metadata",
        "select_thumbnail",
        "render_thumbnail",
        "encode",
        "upload",
        "set_thumbnail",
        "cleanup",
    ]


def test_metadata_step_writes_metadata_json_with_recorded_date(ws, job):
    run_step(job, "metadata", noop)
    metadata = utils.get_metadata(utils.workspace_video_path(ws))
    assert metadata.title.endswith("(2026-11-19)")
    assert metadata.title == "Nam/Hùng vs Tú/Long | Cafe Game (2026-11-19)"


def test_metadata_step_drops_blank_names_and_defaults_tournament(ws, job):
    job.match.team1 = ["Nam", " "]
    job.match.tournament = ""
    run_step(job, "metadata", noop)
    metadata = utils.get_metadata(utils.workspace_video_path(ws))
    assert metadata.title == (
        f"Nam vs Tú/Long | {config.DEFAULT_TOURNAMENT} (2026-11-19)"
    )


def test_steps_pass_segments_and_paths(ws, job, monkeypatch):
    seen = {}

    def fake_render_match(segments, source_dir, output_path, progress=None):
        seen.update(segments=segments, source_dir=source_dir, output=output_path)
        progress(50.0)
        return str(output_path)

    monkeypatch.setattr(video_overlay, "render_match", fake_render_match)
    reported = []
    run_step(job, "encode", reported.append)
    assert seen["segments"] == job.match.segments
    assert seen["source_dir"] == config.INPUT_DIR
    assert seen["output"] == ws / utils.PROCESSED_VIDEO_NAME
    assert reported == [50.0]


def test_each_step_skips_when_its_output_exists(ws, job, calls):
    vp = utils.workspace_video_path(ws)
    for path in (
        utils.get_selected_candidate_path(vp),
        utils.get_thumbnail_path(vp),
        utils.get_processed_video_path(vp),
    ):
        path.write_bytes(b"done")

    for step in ("select_thumbnail", "render_thumbnail", "encode"):
        run_step(job, step, noop)

    assert calls.names == []


def test_each_step_calls_its_function_when_output_missing(ws, job, calls):
    for step in ("select_thumbnail", "render_thumbnail", "encode", "upload"):
        run_step(job, step, noop)
    assert calls.names == ["select", "render", "encode", "upload"]


def test_upload_step_never_calls_uploader_when_upload_json_has_video_id(
    ws, job, calls
):
    vp = utils.workspace_video_path(ws)
    utils.get_processed_video_path(vp).write_bytes(b"video")
    uploader.save_upload_record(vp, "already", thumbnail_set=False)

    run_step(job, "upload", noop)

    assert calls.names == []
    assert utils.get_uploaded_record(vp).video_id == "already"


def test_upload_step_treats_already_uploaded_error_as_done(ws, job, monkeypatch):
    vp = utils.workspace_video_path(ws)
    utils.get_processed_video_path(vp).write_bytes(b"video")

    def already(video_path, heartbeat_callback=None):
        raise VideoAlreadyUploadedError("already uploaded")

    monkeypatch.setattr(uploader, "upload_video_with_idempotency", already)
    run_step(job, "upload", noop)  # does not raise


def test_upload_step_requires_the_encoded_video(ws, job, calls):
    with pytest.raises(FileNotFoundError):
        run_step(job, "upload", noop)
    assert calls.names == []


def _run_all_steps(job):
    for step in STEPS:
        run_step(job, step, noop)


def test_cleanup_step_archives_workspace_and_records_players(ws, job, calls):
    _run_all_steps(job)

    archived = config.COMPLETED_DIR / "2026-11-19_m1"
    assert not ws.exists()
    assert archived.is_dir()
    assert not (archived / utils.PROCESSED_VIDEO_NAME).exists()
    for name in (
        utils.METADATA_FILE,
        utils.RENDERED_THUMBNAIL_NAME,
        utils.UPLOADED_FILE,
        "segments.json",
        store.JOB_FILE,
    ):
        assert (archived / name).exists(), name

    final = json.loads((archived / store.JOB_FILE).read_text(encoding="utf-8"))
    assert final["status"] == "done"
    assert final["progress"] == 100
    assert final["youtube_link"] == "https://youtu.be/vid1"

    players = store.load_players()
    for name in ("Nam", "Hùng", "Tú", "Long"):
        assert players[name] == 1


def test_archived_workspace_works_with_rethumbnail(ws, job, calls):
    _run_all_steps(job)
    archived = config.COMPLETED_DIR / "2026-11-19_m1"
    (archived / "manual.jpg").write_bytes(b"manual")

    assert scan_completed_workspaces(config.COMPLETED_DIR) == [archived]
