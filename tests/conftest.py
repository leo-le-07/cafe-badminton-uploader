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
