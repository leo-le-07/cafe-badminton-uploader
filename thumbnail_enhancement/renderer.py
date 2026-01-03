import config
from pathlib import Path

from thumbnail_enhancement import template_a
from thumbnail_enhancement import template_b
from utils import scan_videos
from logger import get_logger
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


def render_thumbnail(video_path: Path, template_name: str = DEFAULT_TEMPLATE) -> str:
    template_module = get_template_module(template_name)
    return template_module.render_thumbnail(video_path)
