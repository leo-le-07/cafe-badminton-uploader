import argparse
import fcntl
import os
import sys
import threading
import webbrowser
from pathlib import Path
from typing import NoReturn, TextIO

from werkzeug.serving import make_server

import config
from app import server, store
from app.jobs import JobQueue
from logger import get_logger
from auth_service import authenticate
from custom_exceptions import MissingThumbnailDataError
from rethumbnail import rethumbnail_video, scan_completed_workspaces


logger = get_logger(__name__)

HOST = "127.0.0.1"
BROWSER_DELAY_SECONDS = 1.0
LOCK_FILE = "app.lock"


class AlreadyRunningError(Exception):
    """Another process already serves this DATA_DIR."""


def acquire_instance_lock(data_dir: Path) -> TextIO:
    """Hold an exclusive lock on DATA_DIR/app.lock for as long as the returned
    file stays open. The OS drops it when the process dies, so a lock file
    left by a crash is harmless."""
    data_dir.mkdir(parents=True, exist_ok=True)
    handle = open(data_dir / LOCK_FILE, "a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise AlreadyRunningError(str(data_dir))
    return handle


def _fail(message: str) -> NoReturn:
    print(message, file=sys.stderr)
    sys.exit(1)


def serve():
    """Run the editor: background job queue plus the local web server.

    Only one process may run per DATA_DIR, and the port is bound before the
    queue starts, so two workers never process the same jobs."""
    url = f"http://{HOST}:{config.APP_PORT}/"
    try:
        instance_lock = acquire_instance_lock(config.DATA_DIR)
    except AlreadyRunningError:
        _fail(
            f"Ứng dụng đã đang chạy với thư mục dữ liệu {config.DATA_DIR}. "
            f"Mở {url} trong trình duyệt."
        )
    try:
        store.seed_players_from_completed()
        queue = JobQueue()
        app = server.create_app(queue)
        try:
            # werkzeug prints the cause and raises SystemExit when bind fails.
            httpd = make_server(HOST, config.APP_PORT, app, threaded=True)
        except (OSError, SystemExit):
            _fail(
                f"Không mở được cổng {config.APP_PORT} trên {HOST}; có thể một "
                "chương trình khác đang dùng cổng này. Đặt APP_PORT trong file "
                ".env sang cổng khác rồi chạy lại."
            )
        queue.start()
        if os.environ.get("CAFE_NO_BROWSER") != "1":
            opener = threading.Timer(
                BROWSER_DELAY_SECONDS, webbrowser.open, args=(url,)
            )
            opener.daemon = True
            opener.start()
        logger.info(f"Editor running at {url}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            # Stop the queue first: it aborts a running encode or upload at
            # its next progress report, and the step resumes on next start.
            queue.stop()
            httpd.server_close()
    finally:
        instance_lock.close()


def cmd_auth(args):
    try:
        authenticate()
        logger.info("Authentication completed successfully")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)


def cmd_rethumbnail(args):
    workspaces = scan_completed_workspaces(config.COMPLETED_DIR)
    if not workspaces:
        logger.info("No workspaces with manual thumbnails found in COMPLETED_DIR")
        return
    for workspace_dir in workspaces:
        try:
            rethumbnail_video(workspace_dir)
            logger.info(f"Thumbnail updated successfully for {workspace_dir.name}")
        except FileNotFoundError as e:
            logger.error(f"{workspace_dir.name}: {e}")
        except RuntimeError as e:
            logger.error(f"{workspace_dir.name}: {e}")
        except MissingThumbnailDataError as e:
            logger.error(f"{workspace_dir.name}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Cafe Badminton uploader. Without a command, opens the match editor.",
    )

    subparsers = parser.add_subparsers(
        dest="command", help="Command to execute", metavar="COMMAND"
    )

    parser_auth = subparsers.add_parser(
        "auth",
        help="Authenticate with Google OAuth service",
        description="Open browser for OAuth authentication and save token for future use",
    )
    parser_auth.set_defaults(func=cmd_auth)

    parser_rethumbnail = subparsers.add_parser(
        "rethumbnail",
        help="Re-render and re-set thumbnails for all completed videos with a manual image",
        description=(
            "Scans COMPLETED_DIR for workspace folders containing a manually dropped image. "
            "For each one found, re-renders via the thumbnail template and sets it on YouTube. "
            "The manual image is deleted after successful processing."
        ),
    )
    parser_rethumbnail.set_defaults(func=cmd_rethumbnail)

    args = parser.parse_args()

    if not args.command:
        serve()
        return

    args.func(args)


if __name__ == "__main__":
    main()
