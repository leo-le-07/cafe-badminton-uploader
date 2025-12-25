import torch
from PIL import Image
import clip
from dataclasses import dataclass

from thumbnail_ranking.quality_filter import ImageMetrics


@dataclass(frozen=True)
class CLIPConfig:
    model_name: str = "ViT-B/32"
    device: str = "cuda"


@dataclass(frozen=True)
class RankedImage:
    metrics: ImageMetrics
    clip_score: float
    rank: int


POSITIVE_PROMPTS = [
    "badminton smash",
    "badminton jump smash",
    "badminton net kill",
    "badminton defensive dive",
    "badminton fast rally",
    "badminton doubles rally",
    "professional badminton match",
]

NEGATIVE_PROMPTS = [
    "empty badminton court",
    "badminton players standing still",
    "badminton players walking",
    "badminton audience crowd",
    "person walking across the frame",
    "out of focus photo",
]


def get_device() -> str:
    return "cuda" if torch.cuda.is_available() else "cpu"


def calculate_clip_scores(
    metrics_list: list[ImageMetrics],
    config: CLIPConfig,
    positive_prompts=POSITIVE_PROMPTS,
    negative_prompts=NEGATIVE_PROMPTS,
) -> list[RankedImage]:
    model, preprocess = clip.load(config.model_name, config.device)

    images = [
        preprocess(Image.open(metrics.path)).unsqueeze(0) for metrics in metrics_list
    ]
    batched_image_tensor = torch.cat(images).to(config.device)
    batched_positive_texts_tensor = clip.tokenize(positive_prompts).to(config.device)
    batched_negative_texts_tensor = clip.tokenize(negative_prompts).to(config.device)

    with torch.no_grad():
        image_features = model.encode_image(batched_image_tensor)
        pos_text_features = model.encode_text(batched_positive_texts_tensor)
        neg_text_features = model.encode_text(batched_negative_texts_tensor)

        # 1) L2 normalize for cosine similarity
        image_features /= image_features.norm(dim=-1, keepdim=True)
        pos_text_features /= pos_text_features.norm(dim=-1, keepdim=True)
        neg_text_features /= neg_text_features.norm(dim=-1, keepdim=True)

        # 2) Similarity computation
        pos_sims = image_features @ pos_text_features.T
        neg_sims = image_features @ neg_text_features.T

        # 3) Aggregate scores
        pos_max = pos_sims.max(dim=1).values
        neg_max = neg_sims.max(dim=1).values

        # 4) Final CLIP scores
        clip_scores = pos_max - 0.5 * neg_max

    scored = list(zip(metrics_list, clip_scores.tolist()))
    scored.sort(key=lambda x: x[1], reverse=True)
    ranked = [
        RankedImage(metrics=m, clip_score=s, rank=i + 1)
        for i, (m, s) in enumerate(scored)
    ]

    return ranked


def rank_images(
    metrics_list: list[ImageMetrics],
) -> list[RankedImage]:
    device = get_device()
    config = CLIPConfig(device=device)
    ranked = calculate_clip_scores(
        metrics_list, config, POSITIVE_PROMPTS, NEGATIVE_PROMPTS
    )

    return ranked
