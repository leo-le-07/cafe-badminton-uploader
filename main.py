import argparse
import sys

import config
from logger import get_logger
from auth_service import authenticate
from custom_exceptions import MissingThumbnailDataError
from rethumbnail import rethumbnail_video, scan_completed_workspaces


logger = get_logger(__name__)


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
        description="Cafe Badminton uploader",
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
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
