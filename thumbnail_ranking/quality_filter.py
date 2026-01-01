from pathlib import Path
from dataclasses import dataclass
from typing import Any

import cv2
import imagehash
import numpy as np
from PIL import Image
from logger import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class QualityThresholds:
    min_brightness: float = 110.0
    max_brightness: float = 210.0
    min_contrast: float = 38.0
    min_sharpness: float = 120.0
    min_edge_density: float = 0.07
    dup_distance: int = 8


@dataclass(frozen=True)
class ImageMetrics:
    path: str
    filename: str
    brightness: float
    contrast: float
    sharpness: float
    edge_density: float
    phash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "filename": self.filename,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "sharpness": self.sharpness,
            "edge_density": self.edge_density,
            "phash": self.phash,
        }

    def get_phash(self) -> imagehash.ImageHash:
        return imagehash.hex_to_hash(self.phash)


def calculate_image_metrics(image_path: Path) -> ImageMetrics | None:
    image_array = cv2.imread(str(image_path))
    if image_array is None:
        return None

    grayscale = cv2.cvtColor(image_array, cv2.COLOR_BGR2GRAY)

    brightness = float(np.mean(grayscale))  # type: ignore
    contrast = float(np.std(grayscale))  # type: ignore
    sharpness = float(cv2.Laplacian(grayscale, cv2.CV_64F).var())

    edges = cv2.Canny(grayscale, threshold1=50, threshold2=150)
    edge_pixels = int(np.count_nonzero(edges))
    total_pixels = int(edges.size)
    edge_density = float(edge_pixels / total_pixels)

    perceptual_hash = imagehash.phash(Image.open(image_path))
    phash_str = str(perceptual_hash)

    return ImageMetrics(
        path=str(image_path),
        filename=image_path.name,
        brightness=brightness,
        contrast=contrast,
        sharpness=sharpness,
        edge_density=edge_density,
        phash=phash_str,
    )


def collect_image_metrics_from_folder(folder_path: Path) -> list[ImageMetrics]:
    image_extensions = ("*.jpg", "*.jpeg", "*.png")
    image_paths = sorted(
        path for extension in image_extensions for path in folder_path.glob(extension)
    )

    metrics_list = []
    for image_path in image_paths:
        metrics = calculate_image_metrics(image_path)
        if metrics is not None:
            metrics_list.append(metrics)

    return metrics_list


def passes_quality_check(metrics: ImageMetrics, thresholds: QualityThresholds) -> bool:
    return (
        thresholds.min_brightness < metrics.brightness < thresholds.max_brightness
        and metrics.contrast > thresholds.min_contrast
        and metrics.sharpness > thresholds.min_sharpness
        and metrics.edge_density > thresholds.min_edge_density
    )


def filter_by_quality_thresholds(
    metrics_list: list[ImageMetrics], thresholds: QualityThresholds
) -> list[ImageMetrics]:
    return [
        metrics for metrics in metrics_list if passes_quality_check(metrics, thresholds)
    ]


def calculate_statistics(
    metrics_list: list[ImageMetrics],
) -> dict[str, np.ndarray]:
    metric_names = ["brightness", "contrast", "sharpness", "edge_density"]
    statistics = {}

    for metric_name in metric_names:
        values = [getattr(metrics, metric_name) for metrics in metrics_list]
        if values:
            percentiles = np.percentile(values, [5, 25, 50, 75, 90, 95])
            statistics[metric_name] = percentiles

    return statistics


def print_statistics(statistics: dict[str, np.ndarray]) -> None:
    """Print statistics to logger (kept function name for backward compatibility)."""
    for metric_name, percentiles in statistics.items():
        logger.info(f"{metric_name} {percentiles}")


def calculate_adaptive_thresholds(
    statistics: dict[str, np.ndarray],
) -> QualityThresholds:
    PERCENTILE_5TH = 0
    PERCENTILE_25TH = 1
    PERCENTILE_95TH = 5

    brightness_percentiles = statistics.get("brightness", np.array([0, 0, 0, 0, 0, 0]))
    contrast_percentiles = statistics.get("contrast", np.array([0, 0, 0, 0, 0, 0]))
    sharpness_percentiles = statistics.get("sharpness", np.array([0, 0, 0, 0, 0, 0]))
    edge_density_percentiles = statistics.get(
        "edge_density", np.array([0, 0, 0, 0, 0, 0])
    )

    min_brightness = float(
        (
            brightness_percentiles[PERCENTILE_5TH]
            + brightness_percentiles[PERCENTILE_25TH]
        )
        / 2
    )
    max_brightness = float(brightness_percentiles[PERCENTILE_95TH])
    min_contrast = float(contrast_percentiles[PERCENTILE_25TH])
    min_sharpness = float(sharpness_percentiles[PERCENTILE_25TH])
    min_edge_density = float(edge_density_percentiles[PERCENTILE_25TH])

    return QualityThresholds(
        min_brightness=min_brightness,
        max_brightness=max_brightness,
        min_contrast=min_contrast,
        min_sharpness=min_sharpness,
        min_edge_density=min_edge_density,
    )


def are_images_similar(
    metrics1: ImageMetrics, metrics2: ImageMetrics, max_distance: int
) -> bool:
    hash1 = metrics1.get_phash()
    hash2 = metrics2.get_phash()
    hash_distance = hash1 - hash2
    return hash_distance <= max_distance


def remove_duplicate_images(
    metrics_list: list[ImageMetrics], max_hash_distance: int
) -> list[ImageMetrics]:
    if not metrics_list:
        return []

    unique_metrics = [metrics_list[0]]

    for current_metrics in metrics_list[1:]:
        is_duplicate = any(
            are_images_similar(current_metrics, existing_metrics, max_hash_distance)
            for existing_metrics in unique_metrics
        )

        if not is_duplicate:
            unique_metrics.append(current_metrics)

    return unique_metrics
