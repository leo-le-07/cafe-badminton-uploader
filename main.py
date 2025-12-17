import argparse
import sys

from video_prep import run as run_video_prep
from thumbnail_select import run as run_thumbnail_select
from thumbnail_enhancement import run as run_thumbnail_enhancement
from uploader import run as run_uploader


def stage_prepare(args):
    print("=" * 60)
    print("Stage 1: Video Preparation")
    print("=" * 60)
    run_video_prep()
    print("Completed\n")


def stage_select(args):
    print("=" * 60)
    print("Stage 2: Thumbnail Selection")
    print("=" * 60)
    run_thumbnail_select()
    print("Completed\n")


def stage_enhance(args):
    print("=" * 60)
    print("Stage 3: Thumbnail Enhancement")
    print("=" * 60)
    run_thumbnail_enhancement()
    print("Completed\n")


def stage_upload(args):
    print("=" * 60)
    print("Stage 4: Upload to YouTube")
    print("=" * 60)
    run_uploader()
    print("Completed\n")


def stage_all(args):
    stages = [
        ("prepare", stage_prepare),
        ("select", stage_select),
        ("enhance", stage_enhance),
        ("upload", stage_upload),
    ]

    for stage_name, stage_func in stages:
        try:
            stage_func(args)
        except Exception as e:
            print(f"\n\n❌ Error in stage '{stage_name}': {e}")
            print("Fix the issue and run individual stages to continue.")
            sys.exit(1)

    print("=" * 60)
    print("✓ All stages completed successfully!")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="YouTube Video Uploader - Process and upload badminton videos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all stages in order
  python main.py all

  # Run individual stages
  python main.py prepare
  python main.py select
  python main.py enhance
  python main.py upload

  # Get help for a specific stage
  python main.py prepare --help
        """,
    )

    subparsers = parser.add_subparsers(
        dest="stage", help="Stage to execute", metavar="STAGE"
    )

    parser_prepare = subparsers.add_parser(
        "prepare",
        help="Prepare videos: create metadata and frame candidates",
        description="Stage 1: Extract frames from videos and create metadata files",
    )
    parser_prepare.set_defaults(func=stage_prepare)

    parser_select = subparsers.add_parser(
        "select",
        help="Select thumbnails: interactive selection from candidates",
        description="Stage 2: Interactively select the best thumbnail from candidates",
    )
    parser_select.set_defaults(func=stage_select)

    # Stage: enhance
    parser_enhance = subparsers.add_parser(
        "enhance",
        help="Enhance thumbnails: render final thumbnail with graphics",
        description="Stage 3: Enhance selected thumbnail with graphics and text",
    )
    parser_enhance.set_defaults(func=stage_enhance)

    parser_upload = subparsers.add_parser(
        "upload",
        help="Upload videos: upload to YouTube with thumbnail",
        description="Stage 4: Upload videos and thumbnails to YouTube",
    )
    parser_upload.set_defaults(func=stage_upload)

    parser_all = subparsers.add_parser(
        "all",
        help="Run all stages in order (prepare → select → enhance → upload)",
        description="Execute all stages sequentially: prepare, select, enhance, upload",
    )
    parser_all.set_defaults(func=stage_all)

    args = parser.parse_args()

    if not args.stage:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
