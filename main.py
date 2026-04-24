import argparse
import asyncio
import sys
from pathlib import Path

import config
import utils
from temporal.client import (
    VideoWorkflowOptions,
    get_client,
    start_video_workflow,
)
from logger import get_logger
from auth_service import authenticate, validate_auth
from temporal.worker import main as worker_main
from temporal.activities import (
    create_metadata_activity,
    render_thumbnail_activity,
    upload_video_activity,
    auto_select_thumbnail_activity,
    set_thumbnail_activity,
    update_video_visibility_activity,
    cleanup_activity,
)
from video_overlay import add_video_overlays, render_cafe_game_overlay, render_thanks_overlay, get_video_dimensions


logger = get_logger(__name__)


async def cmd_start(args):
    try:
        validate_auth()
    except Exception as e:
        logger.error(f"YouTube authentication failed: {e}. Run 'uv run main.py auth' to re-authenticate.")
        sys.exit(1)

    videos = list(utils.scan_videos(config.INPUT_DIR))

    if not videos:
        logger.warning("No videos found in input directory")
        return

    logger.info(f"Found {len(videos)} video(s)")

    client = await get_client()

    for video_path in videos:
        try:
            options = VideoWorkflowOptions(
                video_path=str(video_path), top_n=config.TOP_RANKED_CANDIDATES_NUM
            )
            await start_video_workflow(client, options)
        except Exception as e:
            logger.error(f"Failed to start workflow for {video_path.name}: {e}")


def cmd_auth(args):
    try:
        authenticate()
        logger.info("Authentication completed successfully")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)


async def cmd_worker(args):
    logger.info("Starting Temporal worker...")
    try:
        await worker_main()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Worker error: {e}")
        sys.exit(1)


def cmd_debug(args):
    step = args.step
    video_path = args.video_path

    activities = {
        "metadata": create_metadata_activity,
        "render": render_thumbnail_activity,
        "upload": upload_video_activity,
        "auto-select-thumbnail": auto_select_thumbnail_activity,
        "set-thumbnail": set_thumbnail_activity,
        "update-visibility": update_video_visibility_activity,
        "cleanup": cleanup_activity,
    }

    if step not in activities:
        logger.error(
            f"Unknown step: {step}\nAvailable steps: {', '.join(activities.keys())}"
        )
        sys.exit(1)

    logger.info(f"Running step '{step}' for {video_path}")

    try:
        result = activities[step](video_path)
        logger.info(f"Success: {result}")
        return result
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def cmd_test_overlay(args):
    input_path = args.input_video
    p = Path(input_path)
    output_path = args.output or str(p.parent / f"{p.stem}_overlay.mov")

    if not p.exists():
        logger.error(f"Input video not found: {input_path}")
        sys.exit(1)

    logger.info(f"Applying overlays to {input_path} → {output_path}")
    try:
        result = add_video_overlays(input_path, output_path=output_path)
        logger.info(f"Done: {result}")
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Temporal Workflow Manager - Start and manage video processing workflows",
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

    parser_start = subparsers.add_parser(
        "start",
        help="Start workflows for all videos in input directory",
        description="Scan input directory and start a workflow for each video",
    )
    parser_start.set_defaults(func=lambda args: asyncio.run(cmd_start(args)))

    parser_worker = subparsers.add_parser(
        "worker",
        help="Start Temporal worker (long-running process)",
        description="Start a long-running worker process that executes workflows and activities. "
        "Runs until interrupted (Ctrl+C).",
    )
    parser_worker.set_defaults(func=lambda args: asyncio.run(cmd_worker(args)))

    parser_debug = subparsers.add_parser(
        "debug",
        help="Debug individual workflow steps",
        description="Run individual workflow steps for debugging without executing the full workflow",
    )
    parser_debug.add_argument(
        "step",
        choices=[
            "metadata",
            "render",
            "upload",
            "auto-select-thumbnail",
            "set-thumbnail",
            "update-visibility",
            "cleanup",
        ],
        help="Step to execute",
    )
    parser_debug.add_argument(
        "video_path",
        help="Path to the video file",
    )
    parser_debug.set_defaults(func=cmd_debug)

    parser_test_overlay = subparsers.add_parser(
        "test-overlay",
        help="Apply video text overlays to a video file for visual testing",
        description="Apply CAFE GAME and THANKS FOR WATCHING overlays to any video file without running the full Temporal workflow.",
    )
    parser_test_overlay.add_argument(
        "input_video",
        help="Path to the input video file",
    )
    parser_test_overlay.add_argument(
        "--output",
        default=None,
        help="Output path for the processed video (default: same directory as input, with _overlay suffix)",
    )
    parser_test_overlay.set_defaults(func=cmd_test_overlay)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
