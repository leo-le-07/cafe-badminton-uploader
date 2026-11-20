import os
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv, find_dotenv

import constants


def env_file_to_load(
    app_env: str | None, find: Callable[[str], str] = find_dotenv
) -> tuple[str | None, str | None]:
    """The env file to load and a warning to print, either of which may be None.

    There is one env file, `.env`. APP_ENV=test loads none and reads only the
    process environment (tests/conftest.py sets it), so a developer's `.env`
    can never point the tests at real folders. Any other APP_ENV is ignored:
    Dev or Production is chosen in the editor, not at start-up.
    """
    if app_env == "test":
        return None, None
    path = find(".env")
    if not path:
        raise FileNotFoundError(
            "Environment file not found: copy env.template to .env and adjust the values."
        )
    warning = None
    if app_env:
        warning = (
            f"APP_ENV={app_env} is no longer used: .env is always loaded. "
            "Choose Dev or Production in the editor."
        )
    return path, warning


_dotenv_path, _warning = env_file_to_load(os.getenv("APP_ENV"))
if _warning:
    print(f"Warning: {_warning}")
if _dotenv_path:
    load_dotenv(dotenv_path=_dotenv_path, override=True)
    print(f"Loaded environment variables from {Path(_dotenv_path).name}")


def get_env_path(var_name: str, create_if_missing: bool = False) -> Path:
    path_str = os.getenv(var_name)

    if not path_str:
        raise ValueError(f"Missing required environment variable: {var_name}")

    path = Path(path_str).resolve()

    if create_if_missing:
        path.mkdir(parents=True, exist_ok=True)

    if not create_if_missing and not path.exists():
        raise FileNotFoundError(f"Directory does not exist: {path}")
    return path


INPUT_DIR = get_env_path("INPUT_DIR", create_if_missing=True)

COMPLETED_DIR = get_env_path("COMPLETED_DIR", create_if_missing=True)

CANDIDATE_THUMBNAIL_NUM = int(os.getenv("CANDIDATE_THUMBNAIL_NUM", 10))

LOGO_PATH = Path(os.getenv("LOGO_PATH", "assets/logo.png"))

DATA_DIR = Path(os.getenv("DATA_DIR") or "./data").resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_APP_PORT = 8790
APP_PORT = int(os.getenv("APP_PORT") or DEFAULT_APP_PORT)

DEFAULT_TOURNAMENT = constants.DEFAULT_TOURNAMENT

MODES = constants.MODES
DEFAULT_MODE = constants.DEFAULT_MODE

QUOTA_RETRY_HOURS = int(os.getenv("QUOTA_RETRY_HOURS") or 4)
