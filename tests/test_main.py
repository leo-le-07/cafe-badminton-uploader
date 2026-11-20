import sys
import threading

import pytest

import config
import main


class Recorder:
    def __init__(self):
        self.events = []
        self.queues = []
        self.bind_args = None


class FakeQueue:
    def __init__(self, rec):
        self.rec = rec
        rec.queues.append(self)

    def start(self):
        self.rec.events.append("start")

    def stop(self):
        self.rec.events.append("stop")


class FakeServer:
    def __init__(self, rec, serve_error=None):
        self.rec = rec
        self.serve_error = serve_error

    def serve_forever(self):
        self.rec.events.append("serve")
        if self.serve_error:
            raise self.serve_error

    def server_close(self):
        self.rec.events.append("close")


@pytest.fixture
def rec(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.setenv("CAFE_NO_BROWSER", "1")
    monkeypatch.setattr(
        main.webbrowser, "open", lambda url: pytest.fail("browser opened")
    )
    r = Recorder()
    monkeypatch.setattr(main, "JobQueue", lambda: FakeQueue(r))
    return r


def fake_bind(monkeypatch, rec, error=None, serve_error=None):
    def make_server(host, port, app, **kwargs):
        rec.bind_args = (host, port, kwargs)
        if error is not None:
            raise error
        rec.events.append("bind")
        return FakeServer(rec, serve_error)

    monkeypatch.setattr(main, "make_server", make_server)


def test_default_command_binds_localhost_only(rec, monkeypatch):
    fake_bind(monkeypatch, rec)

    main.main()

    host, port, kwargs = rec.bind_args
    assert host == "127.0.0.1"
    assert port == config.APP_PORT
    assert kwargs["threaded"] is True
    assert rec.events == ["bind", "start", "serve", "stop", "close"]
    assert (config.DATA_DIR / "players.json").exists()  # players seeded


def test_default_port_is_8790():
    assert config.DEFAULT_APP_PORT == 8790


def test_ctrl_c_stops_the_queue_then_closes_the_server(rec, monkeypatch):
    fake_bind(monkeypatch, rec, serve_error=KeyboardInterrupt())

    main.main()

    assert rec.events == ["bind", "start", "serve", "stop", "close"]


@pytest.mark.parametrize(
    "error", [SystemExit(1), OSError(48, "Address already in use")]
)
def test_port_in_use_exits_without_starting_the_queue(rec, monkeypatch, capsys, error):
    # werkzeug prints its own message and raises SystemExit(1) when bind fails.
    fake_bind(monkeypatch, rec, error=error)

    with pytest.raises(SystemExit) as exit_info:
        main.main()

    assert exit_info.value.code not in (0, None)
    assert "start" not in rec.events
    err = capsys.readouterr().err
    assert str(config.APP_PORT) in err and "APP_PORT" in err


def test_second_instance_exits_without_building_a_queue(rec, monkeypatch, capsys):
    fake_bind(monkeypatch, rec)
    held = main.acquire_instance_lock(config.DATA_DIR)
    try:
        with pytest.raises(SystemExit) as exit_info:
            main.main()
    finally:
        held.close()

    assert exit_info.value.code not in (0, None)
    assert rec.queues == [] and rec.bind_args is None
    err = capsys.readouterr().err
    assert "đang chạy" in err and f"http://127.0.0.1:{config.APP_PORT}/" in err


def test_instance_lock_is_exclusive_until_released(tmp_path):
    first = main.acquire_instance_lock(tmp_path / "data")
    with pytest.raises(main.AlreadyRunningError):
        main.acquire_instance_lock(tmp_path / "data")
    first.close()
    main.acquire_instance_lock(tmp_path / "data").close()


def test_lock_is_released_when_the_server_stops(rec, monkeypatch):
    fake_bind(monkeypatch, rec)
    main.main()
    main.acquire_instance_lock(config.DATA_DIR).close()


def test_default_command_opens_the_editor_in_a_browser(rec, monkeypatch):
    fake_bind(monkeypatch, rec)
    monkeypatch.delenv("CAFE_NO_BROWSER")
    monkeypatch.setattr(main, "BROWSER_DELAY_SECONDS", 0)
    opened = []
    done = threading.Event()

    def fake_open(url):
        opened.append(url)
        done.set()

    monkeypatch.setattr(main.webbrowser, "open", fake_open)

    main.main()

    assert done.wait(5)
    assert opened == [f"http://127.0.0.1:{config.APP_PORT}/"]
