import threading
import time
from unittest.mock import MagicMock

import pytest

import auth_service
import config
import media_probe
import uploader
import utils
from app import pipeline, server, store
from app.jobs import JobQueue
from app.models import Session
from media_probe import SourceInfo

RECORDED_AT = {
    "a.mov": "2026-11-19T21:00:00+07:00",
    "b.mov": "2026-11-19T20:00:00+07:00",
    "c.mp4": "2026-11-19T22:00:00+07:00",
}


class FakePipeline:
    def __init__(self):
        self.fail = {}

    def __call__(self, job, step, progress):
        error = self.fail.get((job.match.id, step))
        if error is not None:
            raise error
        if step == "upload":
            vp = utils.workspace_video_path(store.workspace_dir(job.match.id))
            uploader.save_upload_record(vp, f"vid-{job.match.id}", thumbnail_set=False)


def fake_probe(path):
    if "broken" in path.name:
        raise ValueError(f"No video stream in {path}")
    return SourceInfo(
        name=path.name,
        duration=600.0,
        fps=30.0,
        width=1920,
        height=1080,
        has_audio=True,
        recorded_at=RECORDED_AT.get(path.name, "2026-11-19T23:00:00+07:00"),
    )


@pytest.fixture(autouse=True)
def dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "INPUT_DIR", tmp_path / "input")
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    (tmp_path / "input").mkdir()
    # No token.json in the working directory: auth_status never reaches the network.
    monkeypatch.chdir(tmp_path)
    auth_service.clear_auth_status_cache()
    monkeypatch.setattr(media_probe, "probe", fake_probe)
    yield tmp_path
    auth_service.clear_auth_status_cache()


@pytest.fixture
def fake():
    return FakePipeline()


@pytest.fixture
def queue(monkeypatch, fake):
    monkeypatch.setattr(pipeline, "run_step", fake)
    return JobQueue()


@pytest.fixture
def client(queue):
    return server.create_app(queue).test_client()


@pytest.fixture
def signed_in(monkeypatch):
    monkeypatch.setattr(
        auth_service, "auth_status", lambda: {"ok": True, "channel": "Cafe"}
    )


def add_source(name, size=100):
    path = config.INPUT_DIR / name
    path.write_bytes(bytes(range(256)) * (size // 256) + bytes(size % 256))
    return path


@pytest.fixture
def source():
    return add_source("a.mov")


def match(id, *segments, team1=("Nam",), team2=("Tú",)):
    return {
        "id": id,
        "match_type": "ms",
        "team1": list(team1),
        "team2": list(team2),
        "tournament": "",
        "segments": [
            {"source": src, "start": start, "end": end} for src, start, end in segments
        ],
    }


def session(sources, *matches, selected=None):
    return {
        "sources": list(sources),
        "matches": list(matches),
        "selected_match_id": selected,
    }


def put(client, body):
    return client.put("/api/session", json=body)


def run_until_idle(queue):
    while queue.run_once():
        pass


def statuses(client):
    return {job["match"]["id"]: job["status"] for job in client.get("/api/jobs").json}


# ---- static and media ----------------------------------------------------------


def test_index_is_served_without_caching(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["Cache-Control"] == "no-store"


def test_media_supports_range(client, source):
    r = client.get("/media/a.mov", headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and len(r.data) == 10
    assert r.data == source.read_bytes()[:10]


def test_media_serves_whole_file(client, source):
    r = client.get("/media/a.mov")
    assert r.status_code == 200 and r.data == source.read_bytes()


@pytest.mark.parametrize(
    "name",
    [
        "../token.json",
        "%2e%2e%2ftoken.json",
        "/etc/hosts",
        "sub/../../x.mov",
        "notes.txt",
        "sub/b.mov",
        "%2e%2e%2finput%2fa.mov",
        "A.MOV",
    ],
)
def test_media_refuses_anything_outside_input_dir(client, source, dirs, name):
    (dirs / "token.json").write_text("{}")
    (dirs / "x.mov").write_bytes(b"x")
    (config.INPUT_DIR / "notes.txt").write_text("notes")
    (config.INPUT_DIR / "sub").mkdir()
    (config.INPUT_DIR / "sub" / "b.mov").write_bytes(b"b")
    assert client.get(f"/media/{name}").status_code == 404


# ---- bootstrap, sources, players -------------------------------------------------


def test_bootstrap_shape(client):
    body = client.get("/api/bootstrap").json
    assert set(body) == {"auth", "defaults", "sources", "session", "jobs", "players"}
    assert body["defaults"] == {
        "tournament": config.DEFAULT_TOURNAMENT,
        "privacy": config.VIDEO_PRIVACY_STATUS,
    }
    assert body["session"] == {"sources": [], "matches": [], "selected_match_id": None}
    assert body["auth"] == SIGNED_OUT


def test_sources_sorted_by_recorded_at_with_problems_last(client):
    for name in ("a.mov", "b.mov", "c.mp4", "broken.mov"):
        add_source(name)
    (config.INPUT_DIR / "notes.txt").write_text("notes")
    store.save_session(Session.from_dict(session(["gone.mov"])))

    sources = client.get("/api/sources").json

    assert [s["name"] for s in sources] == [
        "b.mov",
        "a.mov",
        "c.mp4",
        "broken.mov",
        "gone.mov",
    ]
    b = sources[0]
    assert b["duration"] == 600.0 and b["recorded_at"] == RECORDED_AT["b.mov"]
    assert b["missing"] is False and b["unreadable"] is False
    assert b["archivable"] is False
    assert sources[3] == {
        "name": "broken.mov",
        "missing": False,
        "unreadable": True,
        "archivable": False,
    }
    assert sources[4] == {
        "name": "gone.mov",
        "missing": True,
        "unreadable": False,
        "archivable": False,
    }


def test_players_sorted_by_usage(client):
    store.record_players(["Hùng", "Nam", "Tú"])
    store.record_players(["Nam", "Tú"])
    store.record_players(["Nam"])
    assert client.get("/api/bootstrap").json["players"] == ["Nam", "Tú", "Hùng"]


# ---- session -------------------------------------------------------------------


def test_put_session_persists_and_validates(client, source):
    good = session(["a.mov"], match("m1", ("a.mov", 0, 10)), selected="m1")
    r = put(client, good)
    assert r.status_code == 200 and r.json == {"ok": True}
    assert store.load_session().to_dict() == good
    assert client.get("/api/bootstrap").json["session"] == good

    overlapping = session(
        ["a.mov"], match("m1", ("a.mov", 0, 10)), match("m2", ("a.mov", 5, 20))
    )
    r = put(client, overlapping)
    assert r.status_code == 400
    assert any("chồng lên" in e for e in r.json["errors"])
    assert store.load_session().to_dict() == good


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        {"sources": []},
        {"sources": "a.mov", "matches": [], "selected_match_id": None},
        {"sources": [1], "matches": [], "selected_match_id": None},
        session(["a.mov"], {"id": "m1"}),
        session(["a.mov"], {**match("m1"), "team1": "Nam"}),
        session(["a.mov"], match("m1", ("a.mov", "x", 10))),
        session(["a.mov"], match("m1", ("a.mov", True, 10))),
        {"sources": [], "matches": [], "selected_match_id": 3},
    ],
)
def test_put_session_rejects_malformed_body(client, source, body):
    r = (
        client.put("/api/session", json=body)
        if body is not None
        else client.put(
            "/api/session", data="not json", content_type="application/json"
        )
    )
    assert r.status_code == 400
    assert r.json["errors"] and all(isinstance(e, str) for e in r.json["errors"])
    assert not (config.DATA_DIR / store.SESSION_FILE).exists()


def test_put_session_rejects_source_that_is_not_in_input_dir(client, source):
    r = put(client, session(["a.mov", "nowhere.mov"]))
    assert r.status_code == 400
    assert any("nowhere.mov" in e for e in r.json["errors"])


def test_session_with_missing_source_still_loads(client, source, signed_in):
    stored = session(
        ["a.mov", "gone.mov"],
        match("m1", ("gone.mov", 0, 10)),
        match("m2", ("a.mov", 0, 10)),
    )
    store.save_session(Session.from_dict(stored))

    r = client.get("/api/bootstrap")
    assert r.status_code == 200
    gone = [s for s in r.json["sources"] if s["name"] == "gone.mov"]
    assert gone and gone[0]["missing"] is True
    assert r.json["session"] == stored

    # Still saveable, even with a segment beyond any real duration.
    edited = session(
        ["a.mov", "gone.mov"],
        match("m1", ("gone.mov", 0, 10), ("gone.mov", 5000, 6000)),
        match("m2", ("a.mov", 0, 10)),
    )
    assert put(client, edited).status_code == 200

    r = client.post("/api/jobs", json={"match_ids": ["m1"]})
    assert r.status_code == 400
    assert any("gone.mov" in e for e in r.json["errors"])
    assert statuses(client) == {}


def test_put_session_cannot_change_locked_match(client, signed_in):
    add_source("a.mov")
    add_source("b.mov")
    stored = session(
        ["a.mov", "b.mov"], match("m1", ("a.mov", 0, 10)), match("m2", ("b.mov", 0, 10))
    )
    assert put(client, stored).status_code == 200
    assert client.post("/api/jobs", json={"match_ids": ["m1"]}).status_code == 200

    changed = session(
        ["a.mov", "b.mov"],
        match("m1", ("a.mov", 0, 10), team1=["Hùng"]),
        match("m2", ("b.mov", 0, 10)),
    )
    moved = session(
        ["a.mov", "b.mov"], match("m1", ("a.mov", 0, 12)), match("m2", ("b.mov", 0, 10))
    )
    removed = session(["a.mov", "b.mov"], match("m2", ("b.mov", 0, 10)))
    source_removed = session(["b.mov"], match("m2", ("b.mov", 0, 10)))
    for body in (changed, moved, removed, source_removed):
        r = put(client, body)
        assert r.status_code == 409
        assert r.json["errors"] and "m1" in r.json["errors"][0]
    assert store.load_session().to_dict() == stored

    # Unlocked matches still change freely.
    free = session(
        ["a.mov", "b.mov"],
        match("m1", ("a.mov", 0, 10)),
        match("m2", ("b.mov", 0, 30), team2=["Long"]),
        selected="m2",
    )
    assert put(client, free).status_code == 200


def test_put_session_cannot_reuse_id_of_finished_match(client, queue, signed_in):
    add_source("a.mov")
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10))))
    client.post("/api/jobs", json={"match_ids": ["m1"]})
    run_until_idle(queue)
    assert client.post("/api/sources/a.mov/archive").status_code == 200
    add_source("b.mov")

    r = put(client, session(["b.mov"], match("m1", ("b.mov", 0, 10))))
    assert r.status_code == 409


# ---- jobs ----------------------------------------------------------------------


def test_enqueue_then_jobs_lists_it(client, source, signed_in):
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10)), match("m2")))

    r = client.post("/api/jobs", json={"match_ids": ["m1"]})

    assert r.status_code == 200
    [job] = r.json
    assert job["match"]["id"] == "m1" and job["status"] == "queued"
    assert job["recorded_date"] == "2026-11-19"
    assert client.get("/api/jobs").json == r.json
    assert client.get("/api/bootstrap").json["jobs"] == r.json


def test_enqueue_refused_while_signed_out(client, source):
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10))))
    r = client.post("/api/jobs", json={"match_ids": ["m1"]})
    assert r.status_code == 409
    assert "đăng nhập" in r.json["errors"][0]
    assert statuses(client) == {}


def test_enqueue_is_all_or_nothing(client, signed_in):
    add_source("a.mov")
    add_source("broken.mov")
    put(
        client,
        session(
            ["a.mov", "broken.mov"],
            match("m1", ("a.mov", 0, 10)),
            match("m2", ("a.mov", 20, 30), team2=[" "]),
            match("m3", ("broken.mov", 0, 10)),
        ),
    )

    r = client.post("/api/jobs", json={"match_ids": ["m1", "m2", "m3", "nope"]})

    assert r.status_code == 400
    errors = " | ".join(r.json["errors"])
    assert "m2" in errors and "m3" in errors and "nope" in errors
    assert "m1" not in errors
    assert statuses(client) == {}


def test_enqueue_refuses_match_that_already_has_a_job(client, source, signed_in):
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10))))
    assert client.post("/api/jobs", json={"match_ids": ["m1"]}).status_code == 200
    r = client.post("/api/jobs", json={"match_ids": ["m1"]})
    assert r.status_code == 400 and "m1" in r.json["errors"][0]
    assert len(client.get("/api/jobs").json) == 1


def test_enqueue_checks_segments_saved_while_source_was_missing(client, signed_in):
    store.save_session(
        Session.from_dict(session(["a.mov"], match("m1", ("a.mov", 500, 700))))
    )
    add_source("a.mov")  # the file comes back; it is 600 s long
    r = client.post("/api/jobs", json={"match_ids": ["m1"]})
    assert r.status_code == 400
    assert "thời lượng" in r.json["errors"][0]
    assert statuses(client) == {}


@pytest.mark.parametrize(
    "body",
    [
        None,
        {},
        {"match_ids": []},
        {"match_ids": "m1"},
        {"match_ids": [1]},
        {"match_ids": ["m1", "m1"]},
    ],
)
def test_enqueue_rejects_malformed_body(client, signed_in, body):
    r = client.post("/api/jobs", json=body)
    assert r.status_code == 400 and r.json["errors"]


def test_unqueue_conflict_when_uploaded(client, queue, fake, source, signed_in):
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10))))
    client.post("/api/jobs", json={"match_ids": ["m1"]})
    fake.fail[("m1", "set_thumbnail")] = RuntimeError("thumbnail refused")
    run_until_idle(queue)
    assert statuses(client) == {"m1": "error"}

    r = client.post("/api/jobs/m1/unqueue")

    assert r.status_code == 409 and "m1" in r.json["errors"][0]
    assert statuses(client) == {"m1": "error"}


def test_unqueue_conflict_while_upload_session_is_live(
    client, queue, fake, source, signed_in
):
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10))))
    client.post("/api/jobs", json={"match_ids": ["m1"]})
    fake.fail[("m1", "upload")] = ConnectionError("response lost")
    run_until_idle(queue)
    (store.workspace_dir("m1") / uploader.UPLOAD_SESSION_FILE).write_text(
        '{"resumable_uri": "https://up/1", "file_size": 10}'
    )

    r = client.post("/api/jobs/m1/unqueue")

    assert r.status_code == 409
    assert "Thử lại" in r.json["errors"][0]
    assert statuses(client) == {"m1": "error"}
    assert store.workspace_dir("m1").exists()


def test_unqueue_unlocks_match(client, source, signed_in):
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10))))
    client.post("/api/jobs", json={"match_ids": ["m1"]})

    r = client.post("/api/jobs/m1/unqueue")

    assert r.status_code == 200
    assert statuses(client) == {}
    assert store.load_session().matches[0].id == "m1"
    edited = session(["a.mov"], match("m1", ("a.mov", 0, 20)))
    assert put(client, edited).status_code == 200


def test_unqueue_and_retry_unknown_job(client):
    assert client.post("/api/jobs/nope/unqueue").status_code == 404
    assert client.post("/api/jobs/nope/retry").status_code == 404


def test_retry(client, queue, fake, source, signed_in):
    put(client, session(["a.mov"], match("m1", ("a.mov", 0, 10))))
    client.post("/api/jobs", json={"match_ids": ["m1"]})
    assert client.post("/api/jobs/m1/retry").status_code == 409

    fake.fail[("m1", "encode")] = RuntimeError("ffmpeg died")
    run_until_idle(queue)
    assert statuses(client) == {"m1": "error"}

    r = client.post("/api/jobs/m1/retry")
    assert r.status_code == 200
    assert statuses(client) == {"m1": "queued"}


def test_jobs_omit_finished_jobs_outside_the_session(client, queue, signed_in):
    add_source("a.mov")
    add_source("b.mov")
    put(
        client,
        session(
            ["a.mov", "b.mov"],
            match("m1", ("a.mov", 0, 10)),
            match("m2", ("b.mov", 0, 10)),
        ),
    )
    client.post("/api/jobs", json={"match_ids": ["m1"]})
    run_until_idle(queue)
    client.post("/api/jobs", json={"match_ids": ["m2"]})
    assert statuses(client) == {"m1": "done", "m2": "queued"}

    assert client.post("/api/sources/a.mov/archive").status_code == 200

    assert statuses(client) == {"m2": "queued"}
    assert [j["match"]["id"] for j in client.get("/api/bootstrap").json["jobs"]] == [
        "m2"
    ]


# ---- archive -------------------------------------------------------------------


def test_archive_source_refused_while_matches_pending(client, queue, signed_in):
    add_source("a.mov")
    add_source("b.mov")
    put(
        client,
        session(
            ["a.mov", "b.mov"],
            match("m1", ("a.mov", 0, 10)),
            match("m2", ("a.mov", 20, 30)),
        ),
    )
    client.post("/api/jobs", json={"match_ids": ["m1"]})
    run_until_idle(queue)

    assert client.post("/api/sources/a.mov/archive").status_code == 409  # m2 not done
    assert client.post("/api/sources/b.mov/archive").status_code == 409  # no match
    assert client.post("/api/sources/zzz.mov/archive").status_code == 404
    assert (config.INPUT_DIR / "a.mov").exists()
    sources = {s["name"]: s for s in client.get("/api/sources").json}
    assert sources["a.mov"]["archivable"] is False


def test_archive_source_moves_file_and_drops_it_from_session(client, queue, signed_in):
    add_source("a.mov")
    add_source("b.mov")
    put(
        client,
        session(
            ["a.mov", "b.mov"],
            match("m1", ("a.mov", 0, 10)),
            match("m2", ("a.mov", 20, 30), ("b.mov", 0, 10)),
            match("m3", ("b.mov", 20, 30)),
            selected="m1",
        ),
    )
    client.post("/api/jobs", json={"match_ids": ["m1", "m2"]})
    run_until_idle(queue)
    sources = {s["name"]: s for s in client.get("/api/sources").json}
    assert sources["a.mov"]["archivable"] is True
    assert sources["b.mov"]["archivable"] is False  # m3 not done

    r = client.post("/api/sources/a.mov/archive")

    assert r.status_code == 200 and r.json == {"ok": True}
    assert not (config.INPUT_DIR / "a.mov").exists()
    assert (config.COMPLETED_DIR / "sources" / "a.mov").exists()
    stored = store.load_session()
    assert stored.sources == ["b.mov"]
    # m2 still has a segment in b.mov, so it stays until b.mov is archived.
    assert [m.id for m in stored.matches] == ["m2", "m3"]
    assert stored.selected_match_id is None
    # The client saves the session back unchanged: still valid.
    assert put(client, stored.to_dict()).status_code == 200

    client.post("/api/jobs", json={"match_ids": ["m3"]})
    run_until_idle(queue)
    assert client.post("/api/sources/b.mov/archive").status_code == 200
    assert store.load_session().to_dict() == session([])


# ---- auth ----------------------------------------------------------------------


SIGNED_OUT = {
    "ok": False,
    "channel": None,
    "login": {"in_progress": False, "error": None},
}


def test_auth_endpoint_reports_not_logged_in_without_token(client):
    assert client.get("/api/auth").json == SIGNED_OUT


def login_state(client):
    return client.get("/api/auth").json["login"]


def wait_for_login_to_end(client):
    deadline = time.monotonic() + 5
    while login_state(client)["in_progress"]:
        assert time.monotonic() < deadline, "login thread did not end"
        time.sleep(0.01)
    return login_state(client)


class FakeLogin:
    """Stands in for auth_service.authenticate: each call blocks until released,
    then raises the next queued error (or succeeds)."""

    def __init__(self):
        self.calls = 0
        self.errors = []
        self.release = threading.Event()

    def __call__(self):
        self.calls += 1
        assert self.release.wait(5)
        if self.errors:
            raise self.errors.pop(0)


@pytest.fixture
def fake_login(monkeypatch):
    login = FakeLogin()
    monkeypatch.setattr(auth_service, "authenticate", login)
    yield login
    login.release.set()


def test_login_runs_in_background_once(client, fake_login):
    assert client.post("/api/auth/login").status_code == 202
    assert client.post("/api/auth/login").status_code == 202
    assert login_state(client) == {"in_progress": True, "error": None}
    assert client.get("/api/bootstrap").json["auth"]["login"]["in_progress"] is True

    fake_login.release.set()

    assert wait_for_login_to_end(client) == {"in_progress": False, "error": None}
    assert fake_login.calls == 1


def test_login_clears_the_auth_cache_when_it_ends(client, fake_login, monkeypatch):
    assert client.get("/api/auth").json["ok"] is False  # cached as signed out
    client.post("/api/auth/login")
    youtube = MagicMock()
    youtube.channels.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "UC1", "snippet": {"title": "Cafe Badminton"}}]
    }
    monkeypatch.setattr(auth_service, "get_client", lambda: youtube)
    assert client.get("/api/auth").json["ok"] is False  # still cached

    fake_login.release.set()
    wait_for_login_to_end(client)

    auth = client.get("/api/auth").json
    assert auth["ok"] is True and auth["channel"] == "Cafe Badminton"


def test_login_failure_is_reported(client, fake_login):
    fake_login.errors.append(RuntimeError("access_denied"))
    fake_login.release.set()
    client.post("/api/auth/login")

    error = wait_for_login_to_end(client)["error"]

    assert error.startswith("Đăng nhập YouTube thất bại") and "access_denied" in error
    assert client.get("/api/bootstrap").json["auth"]["login"]["error"] == error


def test_login_timeout_is_reported(client, fake_login):
    fake_login.errors.append(auth_service.LoginTimeoutError())
    fake_login.release.set()
    client.post("/api/auth/login")
    assert "Hết thời gian" in wait_for_login_to_end(client)["error"]


def test_login_without_client_secret_is_reported(client):
    # The real authenticate(): the working directory has no client_secret.json.
    client.post("/api/auth/login")
    assert "client_secret.json" in wait_for_login_to_end(client)["error"]


def test_login_can_be_retried_after_a_failure(client, fake_login):
    fake_login.errors.append(auth_service.LoginTimeoutError())
    fake_login.release.set()
    client.post("/api/auth/login")
    assert wait_for_login_to_end(client)["error"]

    fake_login.release.clear()
    assert client.post("/api/auth/login").status_code == 202
    assert login_state(client) == {"in_progress": True, "error": None}
    fake_login.release.set()

    assert wait_for_login_to_end(client) == {"in_progress": False, "error": None}
    assert fake_login.calls == 2


@pytest.mark.parametrize(
    "method, path, code, message",
    [
        ("get", "/api/nope", 404, "Không tìm thấy"),
        ("delete", "/api/session", 405, "Phương thức"),
    ],
)
def test_http_errors_on_api_are_vietnamese_json(client, method, path, code, message):
    r = getattr(client, method)(path)
    assert r.status_code == code
    assert r.json["errors"] and message in r.json["errors"][0]


def test_unexpected_error_answers_vietnamese_json(queue, monkeypatch):
    app = server.create_app(queue)

    def broken():
        raise RuntimeError("boom")

    monkeypatch.setattr(store, "load_session", broken)
    r = app.test_client().get("/api/jobs")
    assert r.status_code == 500
    assert "Lỗi máy chủ" in r.json["errors"][0]
