import os
from pathlib import Path

import config

REPO = Path(__file__).resolve().parent.parent


def test_tests_run_without_any_dotenv_file():
    assert os.environ["APP_ENV"] == "test"


def test_all_data_dirs_are_isolated_under_the_test_root():
    root = Path(os.environ["CAFE_TEST_ROOT"]).resolve()
    for path in (config.INPUT_DIR, config.COMPLETED_DIR, config.DATA_DIR):
        assert path.resolve().is_relative_to(root), path
    forbidden = {REPO / "input", REPO / "completed", REPO / "data"}
    for path in (config.INPUT_DIR, config.COMPLETED_DIR, config.DATA_DIR):
        assert path.resolve() not in forbidden
