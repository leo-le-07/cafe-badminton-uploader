"""Runs before any test module imports `config`.

APP_ENV=test makes config.py skip every dotenv file, so the folders below are
the only ones the tests can see; each is a fresh temp directory.
"""

import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="cafe_test_"))
os.environ["APP_ENV"] = "test"
os.environ["CAFE_TEST_ROOT"] = str(_root)
os.environ["INPUT_DIR"] = str(_root / "input")
os.environ["COMPLETED_DIR"] = str(_root / "completed")
os.environ["DATA_DIR"] = str(_root / "data")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _trash_dir(tmp_path, monkeypatch):
    """Tests never move anything into the real ~/.Trash."""
    import cleanup

    trash = tmp_path / "trash"
    monkeypatch.setattr(cleanup, "TRASH_DIR", trash)
    return trash
