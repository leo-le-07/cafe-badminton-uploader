from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

LOGO_PATH = Path("assets/logo.png")


def enhance_image_visuals(img_pil: Image.Image) -> Image.Image:
    enhancer_color = ImageEnhance.Color(img_pil)
    img_pil = enhancer_color.enhance(1.5)

    enhancer_contrast = ImageEnhance.Contrast(img_pil)
    img_pil = enhancer_contrast.enhance(1.05)

    enhancer_brightness = ImageEnhance.Brightness(img_pil)
    img_pil = enhancer_brightness.enhance(1.15)

    img_pil = img_pil.convert("RGBA")
    width, height = img_pil.size

    x = np.linspace(-1, 1, width)
    y = np.linspace(-1, 1, height)
    X, Y = np.meshgrid(x, y)

    radius = np.sqrt(X**2 + Y**2)

    mask = np.clip(radius - 0.65, 0, 1)

    vignette_intensity = 140
    alpha_channel = (mask * vignette_intensity).astype(np.uint8)

    black_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    black_layer.putalpha(Image.fromarray(alpha_channel, mode="L"))

    final_img = Image.alpha_composite(img_pil, black_layer)

    return final_img.convert("RGB")


def add_logo(img_pil: Image.Image, logo_path: Path) -> Image.Image:
    if not logo_path.exists():
        print(f"Logo file not found: {logo_path}")
        return img_pil

    img_pil = img_pil.convert("RGBA")
    logo = Image.open(logo_path).convert("RGBA")

    target_width = int(img_pil.width * 0.10)
    aspect_ratio = logo.height / logo.width
    target_height = int(target_width * aspect_ratio)

    logo = logo.resize((target_width, target_height), Image.Resampling.LANCZOS)

    padding = int(img_pil.width * 0.03)
    x = img_pil.width - target_width - padding
    y = padding

    img_pil.paste(logo, (x, y), logo)

    return img_pil.convert("RGB")

