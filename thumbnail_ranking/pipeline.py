from pathlib import Path
import shutil

from thumbnail_ranking.quality_filter import (
    collect_image_metrics_from_folder,
    filter_by_quality_thresholds,
    remove_duplicate_images,
    calculate_statistics,
    calculate_adaptive_thresholds,
)
from thumbnail_ranking.clip_ranker import RankedImage, rank_images
from utils import get_candidate_dir, get_top_ranked_candidates_dir, scan_videos
import config


def rank_and_store_top_candidates(
    video_path: Path,
    top_n: int = 5,
) -> list[RankedImage]:
    candidate_dir = get_candidate_dir(video_path)

    if not candidate_dir.exists():
        raise ValueError(f"Candidates directory does not exist: {candidate_dir}")

    all_metrics = collect_image_metrics_from_folder(candidate_dir)

    if not all_metrics:
        raise ValueError(f"No candidate images found in {candidate_dir}")

    # Always calculate adaptive thresholds based on video statistics
    print(f"  Calculating adaptive thresholds for {len(all_metrics)} candidates...")
    statistics = calculate_statistics(all_metrics)
    quality_thresholds = calculate_adaptive_thresholds(statistics)

    quality_metrics = filter_by_quality_thresholds(all_metrics, quality_thresholds)
    if not quality_metrics:
        raise ValueError("No candidates passed quality filtering")

    deduplicated_metrics = remove_duplicate_images(
        quality_metrics, quality_thresholds.dup_distance
    )

    if not deduplicated_metrics:
        raise ValueError(
            f"All candidates were duplicates after filtering ({len(quality_metrics)} unique, 0 after dedup)"
        )

    ranked_images = rank_images(deduplicated_metrics)
    top_ranked = ranked_images[:top_n]

    if not top_ranked:
        raise ValueError("No ranked images to store")

    top_candidates_dir = get_top_ranked_candidates_dir(video_path)
    top_candidates_dir.mkdir(parents=True, exist_ok=True)

    for existing in top_candidates_dir.glob("*.jpg"):
        existing.unlink()

    copied_paths = []
    for i, ranked in enumerate(top_ranked, start=1):
        source_path = Path(ranked.metrics.path)
        # Name format: rank_1_score_0.1724_frame_14043.jpg
        dest_filename = (
            f"rank_{i}_score_{ranked.clip_score:.4f}_{ranked.metrics.filename}"
        )
        dest_path = top_candidates_dir / dest_filename
        shutil.copy2(source_path, dest_path)
        copied_paths.append(dest_path)

    return top_ranked


def select_best_thumbnail(
    video_path: Path,
) -> Path | None:
    top_ranked = rank_and_store_top_candidates(video_path, top_n=1)

    if not top_ranked:
        return None

    return top_ranked[0].metrics.path


def run():
    videos = scan_videos(config.INPUT_DIR)

    for video_path in videos:
        print(f"Ranking candidates for {video_path.name}...")
        try:
            ranked = rank_and_store_top_candidates(
                video_path, top_n=config.TOP_RANKED_CANDIDATES_NUM
            )
            print(f"  ✓ Ranked and stored top {len(ranked)} candidates")
        except Exception as e:
            print(f"  ✗ Error: {e}")


def run_test():
    videos = list(scan_videos(config.INPUT_DIR))
    if not videos:
        print("No videos found in input directory")
        return

    test_video = videos[0]
    top_ranked = rank_and_store_top_candidates(test_video, top_n=3)

    print(f"Top {len(top_ranked)} thumbnails ranked:")
    for ranked in top_ranked:
        print(f"  {ranked.metrics.filename} (score: {ranked.clip_score:.4f})")


if __name__ == "__main__":
    run_test()
