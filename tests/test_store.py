import json

import pytest

import config
from app.models import Job, Match, Segment, Session
from app.store import (
    delete_workspace,
    list_jobs,
    load_job,
    load_mode,
    load_players,
    load_session,
    load_tournaments,
    record_players,
    record_tournaments,
    save_job,
    save_mode,
    save_session,
    seed_players_from_completed,
    seed_tournaments_from_completed,
    workspace_dir,
)


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    return tmp_path


def _match(id="m1"):
    return Match(
        id=id,
        match_type="md",
        team1=["Nam", "Hùng"],
        team2=["Tú", "Long"],
        tournament="Cafe Game",
        segments=[Segment("a.mov", 1.5, 30.0), Segment("b.mov", 0.0, 12.25)],
    )


def _job(id="m1", queued_at="2026-11-20T10:00:00"):
    return Job(
        match=_match(id),
        recorded_date="2026-11-20",
        status="queued",
        step="metadata",
        progress=0.0,
        error=None,
        youtube_link=None,
        queued_at=queued_at,
    )


def test_session_roundtrip():
    s = Session(["a.mov", "b.mov"], [_match("m1"), _match("m2")], "m2")
    save_session(s)
    assert load_session() == s


def test_missing_session_file_gives_empty_session():
    assert load_session() == Session([], [], None)


def test_corrupt_session_file_is_kept_aside_not_deleted(tmp_path):
    (tmp_path / "session.json").write_text("{ half written")
    assert load_session() == Session([], [], None)
    kept = list(tmp_path.glob("session.json.corrupt-*"))
    assert kept
    assert kept[0].read_text() == "{ half written"


def test_save_session_is_atomic(tmp_path):
    save_session(Session(["a.mov"], [_match()], None))
    assert (tmp_path / "session.json").exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_save_session_keeps_vietnamese_readable(tmp_path):
    save_session(Session(["a.mov"], [_match()], None))
    assert "Hùng" in (tmp_path / "session.json").read_text(encoding="utf-8")


def test_workspace_dir_is_under_data_dir(tmp_path):
    assert workspace_dir("m1") == tmp_path / "workspaces" / "m1"


def test_job_roundtrip():
    job = _job()
    save_job(job)
    assert (workspace_dir("m1") / "job.json").exists()
    assert load_job("m1") == job


def test_load_missing_job_gives_none():
    assert load_job("nope") is None


def test_jobs_listed_in_queue_order():
    save_job(_job("late", "2026-11-20T11:00:00"))
    save_job(_job("early", "2026-11-20T09:00:00"))
    assert [j.match.id for j in list_jobs()] == ["early", "late"]


def test_list_jobs_skips_workspaces_without_job():
    workspace_dir("orphan").mkdir(parents=True)
    save_job(_job("m1"))
    assert [j.match.id for j in list_jobs()] == ["m1"]


def test_list_jobs_without_workspaces_is_empty():
    assert list_jobs() == []


def test_delete_workspace_removes_everything():
    save_job(_job("m1"))
    (workspace_dir("m1") / "thumbnail.jpg").write_bytes(b"x")
    delete_workspace("m1")
    assert not workspace_dir("m1").exists()
    assert load_job("m1") is None


def test_delete_missing_workspace_is_noop():
    delete_workspace("nope")


def test_record_players_counts_usage():
    record_players(["Nam", "Tú"])
    record_players(["Nam"])
    assert load_players() == {"Nam": 2, "Tú": 1}


def test_seed_players_from_completed_runs_once(tmp_path, monkeypatch):
    completed = tmp_path / "completed"
    (completed / "x").mkdir(parents=True)
    (completed / "x" / "metadata.json").write_text(
        json.dumps({"team1_names": ["An"], "team2_names": ["Bình"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "COMPLETED_DIR", completed)

    seed_players_from_completed()
    seed_players_from_completed()

    assert load_players() == {"An": 1, "Bình": 1}


def test_record_tournaments_keeps_most_recent_first_without_case_duplicates():
    record_tournaments([("Cafe Game", "blue"), ("Tứ Hùng", "purple")])
    record_tournaments([("tứ hùng", "red"), (" ", "teal")])
    assert load_tournaments() == [
        {"name": "tứ hùng", "theme": "red"},
        {"name": "Cafe Game", "theme": "blue"},
    ]


def test_record_tournaments_keeps_a_bounded_history():
    record_tournaments([(f"Giải {i}", "red") for i in range(30)])
    recent = load_tournaments()
    assert recent[0]["name"] == "Giải 29" and len(recent) == 10


def test_seed_tournaments_from_completed_runs_once_in_date_order(tmp_path, monkeypatch):
    completed = tmp_path / "completed"
    for folder, metadata in [
        ("2026-11-21_b", {"tournament": "Tứ Hùng", "theme": "green"}),
        ("2026-11-20_a", {"tournament": "Cafe Game"}),  # written before themes
    ]:
        (completed / folder).mkdir(parents=True)
        (completed / folder / "metadata.json").write_text(
            json.dumps(metadata), encoding="utf-8"
        )
    (completed / "2026-11-22_c").mkdir()
    (completed / "2026-11-22_c" / "metadata.json").write_text("{ broken")
    monkeypatch.setattr(config, "COMPLETED_DIR", completed)

    seed_tournaments_from_completed()
    record_tournaments([("Giải X", "red")])
    seed_tournaments_from_completed()

    assert load_tournaments() == [
        {"name": "Giải X", "theme": "red"},
        {"name": "Tứ Hùng", "theme": "green"},
        {"name": "Cafe Game", "theme": ""},
    ]


@pytest.mark.parametrize(
    "content", ["{ half written", '{"Nam": 1}', '["Nam"]', '[{"name": "Nam"}]']
)
def test_corrupt_tournaments_file_gives_empty(tmp_path, content):
    (tmp_path / "tournaments.json").write_text(content)
    assert load_tournaments() == []
    assert [p.read_text() for p in tmp_path.glob("tournaments.json.corrupt-*")] == [
        content
    ]


@pytest.mark.parametrize("content", ["{ half written", '{"match": {}}'])
def test_corrupt_job_file_gives_none_and_is_kept_aside(content):
    workspace_dir("m1").mkdir(parents=True)
    (workspace_dir("m1") / "job.json").write_text(content)
    assert load_job("m1") is None
    kept = list(workspace_dir("m1").glob("job.json.corrupt-*"))
    assert [p.read_text() for p in kept] == [content]


def test_list_jobs_skips_corrupt_job_and_keeps_valid_ones():
    save_job(_job("good"))
    workspace_dir("bad").mkdir(parents=True)
    (workspace_dir("bad") / "job.json").write_text("{ half written")
    assert [j.match.id for j in list_jobs()] == ["good"]
    assert list(workspace_dir("bad").glob("job.json.corrupt-*"))


@pytest.mark.parametrize("content", ["{ half written", '["Nam"]', '{"Nam": "x"}'])
def test_corrupt_players_file_gives_empty_and_recording_recovers(tmp_path, content):
    (tmp_path / "players.json").write_text(content)
    assert load_players() == {}
    assert [p.read_text() for p in tmp_path.glob("players.json.corrupt-*")] == [content]
    record_players(["Nam"])
    assert load_players() == {"Nam": 1}


def _archived(completed, name, job_data):
    folder = completed / name
    folder.mkdir(parents=True)
    (folder / "job.json").write_text(job_data, encoding="utf-8")
    return folder


def test_list_archived_jobs_returns_only_done_jobs_and_never_touches_files(
    tmp_path, monkeypatch
):
    from app.store import list_archived_jobs

    completed = tmp_path / "completed"
    monkeypatch.setattr(config, "COMPLETED_DIR", completed)
    done = _job("m1")
    done.status = "done"
    _archived(completed, "2026-11-20_m1", json.dumps(done.to_dict()))
    _archived(completed, "2026-11-20_m2", json.dumps(_job("m2").to_dict()))
    broken = _archived(completed, "2026-11-20_m3", "{not json")
    legacy = completed / "ms_LeovsKhanh"  # pre-rewrite workspace: no job.json
    legacy.mkdir()
    (legacy / "upload.json").write_text("{}", encoding="utf-8")
    before = sorted(p.relative_to(completed) for p in completed.rglob("*"))

    jobs = list_archived_jobs()

    assert [job.match.id for job in jobs] == ["m1"]
    assert sorted(p.relative_to(completed) for p in completed.rglob("*")) == before
    assert (broken / "job.json").read_text(encoding="utf-8") == "{not json"


def test_list_archived_jobs_without_completed_dir(tmp_path, monkeypatch):
    from app.store import list_archived_jobs

    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "missing")
    assert list_archived_jobs() == []


def test_mode_defaults_to_dev_when_nothing_is_stored():
    assert load_mode() == "dev"


def test_mode_round_trips(data_dir):
    save_mode("production")
    assert load_mode() == "production"
    assert json.loads((data_dir / "mode.json").read_text()) == {"mode": "production"}


@pytest.mark.parametrize(
    "content", ['{"mode": "x"}', "[]", '{"mode": 3}', '{"mode": ["dev"]}', "not json"]
)
def test_unusable_mode_file_falls_back_to_dev_and_is_kept(data_dir, content):
    path = data_dir / "mode.json"
    path.write_text(content)
    assert load_mode() == "dev"
    assert not path.exists()
    assert len(list(data_dir.glob("mode.json.corrupt-*"))) == 1


def test_save_mode_refuses_an_unknown_mode(data_dir):
    with pytest.raises(ValueError):
        save_mode("prod")
    assert not (data_dir / "mode.json").exists()
