import os
from pathlib import Path

import pytest

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


def test_test_env_loads_no_file():
    assert config.env_file_to_load("test", lambda name: "/x/.env") == (None, None)


def test_dotenv_is_the_only_file_looked_for():
    asked = []

    def find(name):
        asked.append(name)
        return "/x/.env"

    assert config.env_file_to_load(None, find) == ("/x/.env", None)
    assert asked == [".env"]


@pytest.mark.parametrize("app_env", ["production", "dev"])
def test_old_app_env_values_still_start_with_a_warning(app_env):
    path, warning = config.env_file_to_load(app_env, lambda name: "/x/.env")
    assert path == "/x/.env"
    assert warning == (
        f"APP_ENV={app_env} is no longer used: .env is always loaded. "
        "Choose Dev or Production in the editor."
    )


def test_missing_dotenv_explains_what_to_do():
    with pytest.raises(FileNotFoundError) as e:
        config.env_file_to_load(None, lambda name: "")
    assert str(e.value) == (
        "Environment file not found: copy env.template to .env and adjust the values."
    )
