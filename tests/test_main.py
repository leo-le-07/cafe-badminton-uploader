import sys
import threading

import pytest
from flask import Flask

import config
import main


class FakeQueue:
    instances = []

    def __init__(self):
        self.calls = []
        FakeQueue.instances.append(self)

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


@pytest.fixture
def served(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "COMPLETED_DIR", tmp_path / "completed")
    monkeypatch.setattr(sys, "argv", ["main.py"])
    monkeypatch.setattr(main, "JobQueue", FakeQueue)
    FakeQueue.instances.clear()
    runs = []

    def fake_run(self, **kwargs):
        runs.append((self, kwargs))

    monkeypatch.setattr(Flask, "run", fake_run)
    return runs


def test_default_command_binds_localhost_only(served, monkeypatch):
    monkeypatch.setenv("CAFE_NO_BROWSER", "1")
    monkeypatch.setattr(
        main.webbrowser, "open", lambda url: pytest.fail("browser opened")
    )

    main.main()

    [(app, kwargs)] = served
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == config.APP_PORT
    assert kwargs["threaded"] is True
    [queue] = FakeQueue.instances
    assert queue.calls == ["start", "stop"]
    assert (config.DATA_DIR / "players.json").exists()  # players seeded


def test_default_command_opens_the_editor_in_a_browser(served, monkeypatch):
    monkeypatch.delenv("CAFE_NO_BROWSER", raising=False)
    opened = []
    done = threading.Event()

    def fake_open(url):
        opened.append(url)
        done.set()

    monkeypatch.setattr(main.webbrowser, "open", fake_open)

    main.main()

    assert done.wait(5)
    assert opened == [f"http://127.0.0.1:{config.APP_PORT}/"]
