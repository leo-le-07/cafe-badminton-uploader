from pathlib import Path

from thumbnail_selection.quality_filter import (
    DEFAULT_THRESHOLDS,
    collect_image_metrics_from_folder,
    filter_by_quality_thresholds,
    remove_duplicate_images,
)

from thumbnail_selection.clip_ranker import rank_images


def run_test():
    test_folder = Path("assets/test_candidates")
    thresholds = DEFAULT_THRESHOLDS

    all_metrics = collect_image_metrics_from_folder(test_folder)
    print(f"Total frames: {len(all_metrics)}")

    quality_metrics = filter_by_quality_thresholds(all_metrics, thresholds)
    print(f"Quality frames: {len(quality_metrics)}")

    deduplicated_metrics = remove_duplicate_images(
        quality_metrics, thresholds.dup_distance
    )
    print(f"Deduplicated frames: {len(deduplicated_metrics)}")

    ranked = rank_images(deduplicated_metrics)
    print(f"Best thumbnail: {ranked[0].metrics.filename}")


if __name__ == "__main__":
    run_test()
