import json

import pytest

import config
import uploader
import utils
from app import store
from app.models import Job, Match, Segment
from cleanup import archive_source, archive_workspace
from custom_exceptions import NoUploadedRecordError


def _job(id="m1"):
    return Job(
        match=Match(
            id=id,
            match_type="ms",
            team1=["Leo"],
            team2=["Khánh"],
            tournament="Cafe Game",
            segments=[Segment("a.mov", 1.0, 20.0), Segment("b.mov", 2.0, 8.5)],
        ),
        recorded_date="2026-11-19",
        status="running",
        step="cleanup",
        progress=0.0,
        error=None,
        youtube_link=None,
        queued_at="2026-11-20T10:00:00",
    )


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    (tmp_path / "input").mkdir()
    (tmp_path / "completed").mkdir()


def _uploaded_workspace(id="m1"):
    store.save_job(_job(id))
    ws = store.workspace_dir(id)
    vp = utils.workspace_video_path(ws)
    utils.get_processed_video_path(vp).write_bytes(b"video")
    (ws / uploader.UPLOAD_SESSION_FILE).write_text("{}", encoding="utf-8")
    (ws / utils.METADATA_FILE).write_text("{}", encoding="utf-8")
    (ws / utils.RENDERED_THUMBNAIL_NAME).write_bytes(b"img")
    uploader.save_upload_record(vp, "vid1", thumbnail_set=True)
    return ws


class TestArchiveWorkspace:
    def test_moves_workspace_into_completed_with_date_prefix(self):
        ws = _uploaded_workspace()
        dest = archive_workspace("m1")
        assert dest == config.COMPLETED_DIR / "2026-11-19_m1"
        assert not ws.exists()
        assert dest.is_dir()

    def test_drops_encoded_video_and_upload_session(self):
        _uploaded_workspace()
        dest = archive_workspace("m1")
        assert not (dest / utils.PROCESSED_VIDEO_NAME).exists()
        assert not (dest / uploader.UPLOAD_SESSION_FILE).exists()

    def test_keeps_job_metadata_thumbnail_and_upload_record(self):
        _uploaded_workspace()
        dest = archive_workspace("m1")
        for name in (
            store.JOB_FILE,
            utils.METADATA_FILE,
            utils.RENDERED_THUMBNAIL_NAME,
            utils.UPLOADED_FILE,
        ):
            assert (dest / name).exists(), name

    def test_writes_segments_json(self):
        _uploaded_workspace()
        dest = archive_workspace("m1")
        segments = json.loads((dest / "segments.json").read_text(encoding="utf-8"))
        assert segments == [
            {"source": "a.mov", "start": 1.0, "end": 20.0},
            {"source": "b.mov", "start": 2.0, "end": 8.5},
        ]

    def test_does_not_overwrite_an_existing_archive(self):
        existing = config.COMPLETED_DIR / "2026-11-19_m1"
        existing.mkdir()
        (existing / "keep.txt").write_text("old", encoding="utf-8")
        _uploaded_workspace()

        dest = archive_workspace("m1")

        assert dest != existing
        assert dest.name.startswith("2026-11-19_m1")
        assert (existing / "keep.txt").read_text(encoding="utf-8") == "old"
        assert (dest / utils.UPLOADED_FILE).exists()

    def test_refuses_when_not_uploaded(self):
        store.save_job(_job())
        ws = store.workspace_dir("m1")
        utils.get_processed_video_path(utils.workspace_video_path(ws)).write_bytes(
            b"video"
        )
        with pytest.raises(NoUploadedRecordError):
            archive_workspace("m1")
        assert (ws / utils.PROCESSED_VIDEO_NAME).exists()

    def test_refuses_when_job_missing(self):
        with pytest.raises(FileNotFoundError):
            archive_workspace("nope")


class TestArchiveSource:
    def test_moves_source_into_completed_sources(self):
        src = config.INPUT_DIR / "IMG_0001.MOV"
        src.write_bytes(b"raw")
        dest = archive_source("IMG_0001.MOV")
        assert dest == config.COMPLETED_DIR / "sources" / "IMG_0001.MOV"
        assert not src.exists()
        assert dest.read_bytes() == b"raw"

    def test_adds_numeric_suffix_instead_of_overwriting(self):
        sources = config.COMPLETED_DIR / "sources"
        sources.mkdir()
        (sources / "IMG_0001.MOV").write_bytes(b"old")
        (sources / "IMG_0001-1.MOV").write_bytes(b"older")
        (config.INPUT_DIR / "IMG_0001.MOV").write_bytes(b"new")

        dest = archive_source("IMG_0001.MOV")

        assert dest == sources / "IMG_0001-2.MOV"
        assert dest.read_bytes() == b"new"
        assert (sources / "IMG_0001.MOV").read_bytes() == b"old"
        assert (sources / "IMG_0001-1.MOV").read_bytes() == b"older"

    def test_missing_source_raises(self):
        with pytest.raises(FileNotFoundError):
            archive_source("missing.mov")

    @pytest.mark.parametrize("name", ["../x.mov", "sub/x.mov", "", ".."])
    def test_rejects_names_that_are_not_plain_file_names(self, name):
        with pytest.raises(ValueError):
            archive_source(name)
