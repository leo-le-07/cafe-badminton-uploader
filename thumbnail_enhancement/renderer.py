from pathlib import Path

from thumbnail_enhancement import template_a
from thumbnail_enhancement import template_b
import utils
from logger import get_logger

logger = get_logger(__name__)

TEMPLATES = {
    "template_a": template_a,
    "template_b": template_b,
}

DEFAULT_TEMPLATE = "template_b"


def get_template_module(template_name: str):
    if template_name not in TEMPLATES:
        raise ValueError(
            f"Unknown template: {template_name}. Available templates: {list(TEMPLATES.keys())}"
        )
    return TEMPLATES[template_name]


def render_thumbnail(video_path: str, template_name: str = DEFAULT_TEMPLATE) -> str:
    path = Path(video_path)

    thumbnail_path = utils.get_thumbnail_path(path)
    if thumbnail_path.exists():
        logger.info(f"Thumbnail already rendered, skipping: {thumbnail_path}")
        return str(thumbnail_path)

    template_module = get_template_module(template_name)
    return template_module.render_thumbnail(path)
