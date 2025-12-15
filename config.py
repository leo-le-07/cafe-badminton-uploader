import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


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
CANDIDATE_THUMBNAIL_NUM = int(os.getenv("CANDIDATE_THUMBNAIL_NUM", "5"))

__all__ = [
    "INPUT_DIR",
    "COMPLETED_DIR",
    "CANDIDATE_THUMBNAIL_NUM",
]
