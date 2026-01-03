import argparse
import asyncio
import sys
from pathlib import Path
from typing import List

import config
import utils
from temporal.client import (
    VideoWorkflowOptions,
    get_client,
    start_video_workflow,
)
from temporalio.client import WorkflowHandle
from logger import get_logger
from constants import WORKFLOW_STAGE_WAITING_FOR_SELECTION
from auth_service import authenticate
from temporal.worker import main as worker_main
from temporal.activities import (
    create_metadata_activity,
    create_frame_candidates_activity,
    rank_candidates_activity,
    render_thumbnail_activity,
    upload_video_activity,
    set_thumbnail_activity,
    update_video_visibility_activity,
    cleanup_activity,
)

logger = get_logger(__name__)


async def cmd_start(args):
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


async def get_workflow_handlers_waiting_for_selection(
    client,
) -> List[tuple[str, WorkflowHandle, Path]]:
    workflows = []
    async for workflow_desc in client.list_workflows(
        query='WorkflowType = "ProcessVideoWorkflow" AND ExecutionStatus = "Running"'
    ):
        try:
            handle = client.get_workflow_handle(workflow_desc.id)
            stage = await handle.query("get_stage")
            if stage == WORKFLOW_STAGE_WAITING_FOR_SELECTION:
                video_path_str = await handle.query("get_video_path")
                video_path = Path(video_path_str)
                workflows.append((workflow_desc.id, handle, video_path))
        except Exception as e:
            logger.warning(f"Could not query workflow {workflow_desc.id}: {e}")
            continue
    return workflows


async def cmd_list(args):
    client = await get_client()

    try:
        workflows = await get_workflow_handlers_waiting_for_selection(client)

        if not workflows:
            logger.info("No workflows waiting for selection.")
            return

        logger.info(f"Found {len(workflows)} workflow(s) waiting for selection:")
        for i, (workflow_id, handle, video_path) in enumerate(workflows, start=1):
            logger.info(f"{i}. Workflow ID: {workflow_id} | Video: {video_path.name}")

        logger.info("Use 'select' to process all workflows waiting for selection")

    except Exception as e:
        logger.error(f"Error listing workflows: {e}")
        sys.exit(1)


def cmd_auth(args):
    try:
        authenticate()
        logger.info("Authentication completed successfully")
    except Exception as e:
        logger.error(f"Authentication failed: {e}")
        sys.exit(1)


async def cmd_select(args):
    client = await get_client()

    try:
        workflows = await get_workflow_handlers_waiting_for_selection(client)

        if not workflows:
            logger.info("No workflows waiting for selection.")
            return

        logger.info(f"Processing {len(workflows)} workflow(s) for thumbnail selection")

        from thumbnail_selector import select_thumbnail_with_workflow

        for i, (workflow_id, handle, video_path) in enumerate(workflows, start=1):
            logger.info(f"[{i}/{len(workflows)}] {video_path.name} ({workflow_id})")

            try:
                await select_thumbnail_with_workflow(handle)
            except Exception as e:
                logger.error(f"Error processing workflow {workflow_id}: {e}")
                continue

    except Exception as e:
        logger.error(f"Error selecting thumbnails: {e}")
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
        "frames": create_frame_candidates_activity,
        "rank": rank_candidates_activity,
        "render": render_thumbnail_activity,
        "upload": upload_video_activity,
        "set-thumbnail": set_thumbnail_activity,
        "update-visibility": update_video_visibility_activity,
        "cleanup": cleanup_activity,
    }

    if step not in activities:
        logger.error(
            f"Unknown step: {step}\n"
            f"Available steps: {', '.join(activities.keys())}"
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

    parser_list = subparsers.add_parser(
        "list",
        help="List all workflows waiting for selection",
        description="Query and display all workflows with status WAITING_FOR_SELECTION",
    )
    parser_list.set_defaults(func=lambda args: asyncio.run(cmd_list(args)))

    parser_select = subparsers.add_parser(
        "select",
        help="Select thumbnails for all workflows waiting for selection",
        description="Automatically get all workflows waiting for selection and process each one with thumbnail selector",
    )
    parser_select.set_defaults(func=lambda args: asyncio.run(cmd_select(args)))

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
            "frames",
            "rank",
            "render",
            "upload",
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()

