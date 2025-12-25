import os
from pathlib import Path

from dotenv import load_dotenv, find_dotenv

env = os.getenv("APP_ENV", "dev")
dotenv_path = find_dotenv(f".env.{env}")

if not dotenv_path:
    dotenv_path = find_dotenv(".env")
    if dotenv_path:
        print(f"Warning: .env.{env} not found, using .env instead")
    else:
        raise FileNotFoundError(
            f"Environment file not found: .env.{env} or .env. "
            f"Set APP_ENV environment variable (e.g., APP_ENV=dev or APP_ENV=production)"
        )

load_dotenv(dotenv_path=dotenv_path, override=True)
print(f"Loaded environment variables from {Path(dotenv_path).name}")


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

TOP_RANKED_CANDIDATES_NUM = int(os.getenv("TOP_RANKED_CANDIDATES_NUM", 5))

VIDEO_PRIVACY_STATUS = os.getenv("VIDEO_PRIVACY_STATUS", "private")
