import torch
from transformers import AutoModelForCausalLM
from pathlib import Path
from PIL import Image
import re


def get_device_model():
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"


def get_model():
    model = AutoModelForCausalLM.from_pretrained(
        "vikhyatk/moondream2",
        revision="2025-06-21",
        trust_remote_code=True,
    )

    device_model = get_device_model()
    print(f"device_model: {device_model}")
    model.to(device_model)

    return model


def get_image():
    # image_path = Path("assets/test_candidates/frame_16563.jpg")
    image_path = Path("assets/test_candidates/frame_11162.jpg")
    image = Image.open(image_path).convert("RGB")
    return image


def get_prompt():
    return """
    Rate this image from 1 to 10 as a badminton YouTube thumbnail.

    Rules:
    - If the image is sharp, well-lit, and players are clearly visible, SCORE MUST be 6 or higher.
    - If it shows a clear action moment (smash/rally/net play), SCORE MUST be 8 or higher.
    - Only use 1–3 for blurry/dark/players not visible.

    Respond ONLY:
    SCORE=<1-10>; TAGS=<comma list>; REASON=<one sentence>

    """


def run():
    model = get_model()
    image = get_image()
    prompt = get_prompt().strip()

    # Inference (no gradients)
    with torch.inference_mode():
        result = model.query(image, prompt)

    print("Raw result:")
    print(result)

    # moondream2 typically returns a dict like {"answer": "..."}
    answer = result.get("answer") if isinstance(result, dict) else str(result)
    print("\nParsed answer text:")
    print(answer)

    # Optional: extract SCORE
    m = re.search(r"SCORE\s*=\s*([0-9]+(?:\.[0-9]+)?)", answer or "")
    if m:
        print("\nScore:", float(m.group(1)))
    else:
        print("\nCould not parse SCORE from output (prompt may need tightening).")


if __name__ == "__main__":
    run()
