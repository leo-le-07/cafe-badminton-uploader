import argparse
import asyncio
import sys

import config
import utils
from temporal.client import (
    VideoWorkflowOptions,
    get_client,
    start_video_workflow,
    gen_workflow_id,
)


async def cmd_start(args):
    print("=" * 60)
    print("Starting workflows for videos in input directory")
    print("=" * 60)

    videos = list(utils.scan_videos(config.INPUT_DIR))

    if not videos:
        print("No videos found in input directory")
        return

    print(f"Found {len(videos)} video(s)\n")

    client = await get_client()

    for video_path in videos:
        try:
            workflow_id = gen_workflow_id(video_path)
            options = VideoWorkflowOptions(
                video_path=str(video_path), top_n=config.TOP_RANKED_CANDIDATES_NUM
            )
            await start_video_workflow(client, options)
            print(f"✓ Started workflow for {video_path.name}: {workflow_id}")
        except Exception as e:
            print(f"✗ Failed to start workflow for {video_path.name}: {e}")

    print("\n" + "=" * 60)
    print("Workflow startup completed")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Temporal Workflow Manager - Start and manage video processing workflows",
    )

    subparsers = parser.add_subparsers(
        dest="command", help="Command to execute", metavar="COMMAND"
    )

    parser_start = subparsers.add_parser(
        "start",
        help="Start workflows for all videos in input directory",
        description="Scan input directory and start a workflow for each video",
    )
    parser_start.set_defaults(func=lambda args: asyncio.run(cmd_start(args)))

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
