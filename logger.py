import logging
import os
import sys
from typing import Optional


def setup_logging(
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    enable_temporal_integration: bool = True,
) -> None:
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_string,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )

    if enable_temporal_integration:
        logging.getLogger("temporalio").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("googleapiclient").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


_log_level = logging.INFO
_log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
if hasattr(logging, _log_level_str):
    _log_level = getattr(logging, _log_level_str)

setup_logging(level=_log_level)

