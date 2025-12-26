import argparse
import sys

from video_prep import run as run_video_prep
from thumbnail_ranking.pipeline import run as run_thumbnail_ranking
from thumbnail_selector import run as run_thumbnail_select
from thumbnail_enhancement.renderer import (
    DEFAULT_TEMPLATE,
    run as run_thumbnail_enhancement,
)
from uploader import run as run_uploader
from cleanup import cleanup_uploaded_videos


def stage_prepare(args):
    print("=" * 60)
    print("Stage 1: Video Preparation")
    print("=" * 60)
    run_video_prep()
    print("Completed\n")


def stage_rank(args):
    print("=" * 60)
    print("Stage 2: Thumbnail Ranking")
    print("=" * 60)
    run_thumbnail_ranking()
    print("Completed\n")


def stage_select(args):
    print("=" * 60)
    print("Stage 3: Thumbnail Selection")
    print("=" * 60)
    run_thumbnail_select()
    print("Completed\n")


def stage_enhance(args):
    print("=" * 60)
    print("Stage 4: Thumbnail Enhancement")
    print("=" * 60)
    template_name = getattr(args, "template", DEFAULT_TEMPLATE)
    run_thumbnail_enhancement(template_name=template_name)
    print("Completed\n")


def stage_upload(args):
    print("=" * 60)
    print("Stage 5: Upload to YouTube")
    print("=" * 60)
    run_uploader()
    print("Completed\n")


def stage_cleanup(args):
    print("=" * 60)
    print("Cleanup: Move uploaded videos to completed directory")
    print("=" * 60)
    cleanup_uploaded_videos()
    print("Completed\n")


def stage_all(args):
    stages = [
        ("prepare", stage_prepare),
        ("rank", stage_rank),
        ("select", stage_select),
        ("enhance", stage_enhance),
        ("upload", stage_upload),
        ("cleanup", stage_cleanup),
    ]

    for stage_name, stage_func in stages:
        try:
            stage_func(args)
        except Exception as e:
            print(f"\n\n❌ Error in stage '{stage_name}': {e}")
            print("Fix the issue and run individual stages to continue.")
            sys.exit(1)

    print("=" * 60)
    print("All stages completed successfully!")
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
  python main.py rank
  python main.py select
  python main.py enhance
  python main.py upload
  python main.py cleanup

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

    parser_rank = subparsers.add_parser(
        "rank",
        help="Rank thumbnails: filter and rank candidates using CLIP",
        description="Stage 2: Filter candidates by quality, remove duplicates, and rank using CLIP",
    )
    parser_rank.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of top candidates to store (default: 5)",
    )
    parser_rank.set_defaults(func=stage_rank)

    parser_select = subparsers.add_parser(
        "select",
        help="Select thumbnails: interactive selection from top candidates",
        description="Stage 3: Interactively select the best thumbnail from top-ranked candidates",
    )
    parser_select.set_defaults(func=stage_select)

    parser_enhance = subparsers.add_parser(
        "enhance",
        help="Enhance thumbnails: render final thumbnail with graphics",
        description="Stage 4: Enhance selected thumbnail with graphics and text",
    )
    parser_enhance.add_argument(
        "--template",
        default=DEFAULT_TEMPLATE,
        choices=["template_a", "template_b"],
        help="Thumbnail template to use (default: template_b)",
    )
    parser_enhance.set_defaults(func=stage_enhance)

    parser_upload = subparsers.add_parser(
        "upload",
        help="Upload videos: upload to YouTube with thumbnail",
        description="Stage 5: Upload videos and thumbnails to YouTube",
    )
    parser_upload.set_defaults(func=stage_upload)

    parser_cleanup = subparsers.add_parser(
        "cleanup",
        help="Cleanup: move uploaded videos to completed directory",
        description="Move uploaded videos and their folders to COMPLETED_DIR",
    )
    parser_cleanup.set_defaults(func=stage_cleanup)

    parser_all = subparsers.add_parser(
        "all",
        help="Run all stages in order (prepare → rank → select → enhance → upload)",
        description="Execute all stages sequentially: prepare, rank, select, enhance, upload",
    )
    parser_all.set_defaults(func=stage_all)

    args = parser.parse_args()

    if not args.stage:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
