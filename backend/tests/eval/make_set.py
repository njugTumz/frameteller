"""Build the supervisor eval set from the lighthouse story (docs/supervisor-eval.md). Costs about $0.12.

    cd backend && .venv/bin/python -m tests.eval.make_set ../spikes/out/lighthouse/store

The clean sheets and panels are copied as they are (passes). Each variant is one Muse Image edit
(POST /v1/images/edits, the clean image as the input) that adds one known failure; two reproduce real ones
(Pip's sheet in Ada's green sweater, Pip in a blue vest). Every image is stored as a small webp (768 px).
Labels are written by hand in labels.json after looking at each result: an edit that did not take is
labelled for what it shows, not for what was asked. MODEL_API_KEY comes from .env through the settings
class and is never printed. The lighthouse story is our own synthetic story.
"""

from __future__ import annotations

import base64
import io
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from frameteller.infrastructure.config import load_settings

HERE = Path(__file__).parent
IMAGES = HERE / "images"
PROJECT = "01d74aa8fba54f9ea49537571d4c9b63"
SIDE = 768
SHOTS = {  # shot number -> shot id in the lighthouse project
    1: "ed5ecf944fa342c3b3827edac14f0647",
    2: "73239d16d9e04fc2a2214ab3eabd0227",
    3: "3e86a734e76d4e51a701ee5e5ae58d3a",
    4: "8f80e3a2079d470cb0970b2a244f1983",
    5: "3d9fe77ed4ce484494505eddddf2fc17",
    6: "4124194574404e1fb1b673a13aec739c",
}
KEEP = " Keep everything else exactly the same: composition, style, colours and the other characters."
# name -> (base image, edit prompt)
VARIANTS: dict[str, tuple[str, str]] = {
    "sheet-pip-sweater": ("sheet-pip", "The fox now wears a thick green knitted sweater on his body in both views."),
    "sheet-ada-scarf": ("sheet-ada", "The woman now wears a bright red scarf around her neck in both views."),
    "shot4-pip-vest": ("shot4", "The small orange fox now wears a blue vest."),
    "shot2-ada-hat": ("shot2", "The old woman now wears a wide-brimmed brown hat."),
    "shot2-ada-black-hair": ("shot2", "The old woman's hair is now jet black instead of silver."),
    "shot2-ada-glasses": ("shot2", "The old woman now wears round black glasses."),
    "shot5-extra-cat": ("shot5", "Add a grey cat sitting on the floor beside the woman."),
    "shot6-no-pip": ("shot6", "Remove the fox: the woman sits alone on the rock."),
    "shot6-ada-red-sweater": ("shot6", "The woman's sweater is now bright red instead of green."),
    "shot3-photoreal-pip": ("shot3", "Draw the fox as a photorealistic photo of a real fox; the rest stays sketched."),
    "shot4-pip-cat": ("shot4", "The small orange fox is now a small orange tabby cat."),
    "shot5-more-rain": ("shot5", "Heavier rain streaks on the window glass."),  # control: should still pass
}


def small(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as opened:
        image = opened.convert("RGB")
    image.thumbnail((SIDE, SIDE))
    out = io.BytesIO()
    image.save(out, "WEBP", quality=82)
    return out.getvalue()


def edit(base: bytes, prompt: str, size: str, key: str, url: str) -> bytes:
    body = {
        "model": "muse-image-1.0",
        "prompt": prompt + KEEP,
        "images": [{"image_url": "data:image/webp;base64," + base64.b64encode(base).decode()}],
        "size": size,
        "reasoning_strength": "low",
    }
    request = urllib.request.Request(
        f"{url}/images/edits",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as r:
            return base64.b64decode(json.loads(r.read())["data"][0]["b64_json"])
    except urllib.error.HTTPError as e:
        raise SystemExit(f"images/edits {e.code}: {e.read()[:300]!r}") from None


def main(store: Path) -> None:
    media = store / "media" / "projects" / PROJECT
    full = {
        "sheet-ada": (media / "characters/ada/reference").read_bytes(),
        "sheet-pip": (media / "characters/pip/reference").read_bytes(),
        **{f"shot{n}": (media / f"panels/{sid}/r1/image").read_bytes() for n, sid in SHOTS.items()},
    }
    IMAGES.mkdir(exist_ok=True)
    for name, data in full.items():
        (IMAGES / f"{name}.webp").write_bytes(small(data))
    settings = load_settings(app_env="local")
    key = settings.model_api_key.get_secret_value()
    spent = 0.0
    for name, (base, prompt) in VARIANTS.items():
        if (IMAGES / f"{name}.webp").exists():
            continue  # already made: never pay twice
        size = "1024x1024" if base.startswith("sheet") else "1536x1024"
        (IMAGES / f"{name}.webp").write_bytes(small(edit(full[base], prompt, size, key, settings.meta_base_url)))
        spent += 0.01
        print(f"{name}: done (${spent:.2f})", flush=True)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
