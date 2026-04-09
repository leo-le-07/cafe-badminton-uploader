#!/usr/bin/env python3
"""Quick test script for web-based thumbnail selector."""

import sys
from pathlib import Path

from web_selector.server import select_thumbnail_web

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: uv run python -m web_selector.test_thumbnail_selector <video_path>"
        )
        sys.exit(1)

    video_path = Path(sys.argv[1])

    if not video_path.exists():
        print(f"Error: Video file not found: {video_path}")
        sys.exit(1)

    print(f"Starting thumbnail selector for: {video_path}")
    print("Browser will open automatically. Select a frame to save as thumbnail.")

    try:
        select_thumbnail_web(video_path)
        print("✓ Thumbnail selection completed!")
    except KeyboardInterrupt:
        print("\n✗ Selection cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)
