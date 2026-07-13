"""Generates 14 abstract 'generated scene' placeholder thumbnails, fully offline.

These stand in for SDXL/FLUX output in the Image Generation batch grid demo —
there is no local image model wired up, so each tile is a procedural gradient
with a scene number instead of a real render.
"""

from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
SCENES_DIR = HERE / "scenes"

PALETTES = [
    ((235, 168, 109), (120, 58, 45)),
    ((120, 168, 235), (35, 60, 110)),
    ((201, 140, 219), (78, 40, 96)),
    ((140, 219, 173), (30, 90, 70)),
    ((235, 140, 155), (110, 35, 55)),
    ((214, 201, 120), (100, 88, 30)),
    ((150, 150, 235), (50, 50, 120)),
]

SIZE = (360, 240)


def draw_scene(idx: int) -> Image.Image:
    top, bottom = PALETTES[idx % len(PALETTES)]
    w, h = SIZE
    img = Image.new("RGB", SIZE)
    px = img.load()
    for y in range(h):
        t = y / (h - 1)
        r = int(top[0] * (1 - t) + bottom[0] * t)
        g = int(top[1] * (1 - t) + bottom[1] * t)
        b = int(top[2] * (1 - t) + bottom[2] * t)
        for x in range(w):
            px[x, y] = (r, g, b)

    draw = ImageDraw.Draw(img, "RGBA")
    # a couple of soft abstract shapes so tiles don't look like flat swatches
    draw.ellipse((w * 0.55, h * 0.15, w * 1.05, h * 0.75), fill=(255, 255, 255, 28))
    draw.ellipse((-w * 0.1, h * 0.5, w * 0.45, h * 1.1), fill=(0, 0, 0, 30))

    label = f"Scene {idx + 1}"
    draw.rectangle((10, h - 34, 10 + 13 * len(label), h - 8), fill=(0, 0, 0, 130))
    draw.text((16, h - 30), label, fill=(255, 255, 255, 235))
    return img


def main():
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    for i in range(14):
        draw_scene(i).save(SCENES_DIR / f"scene_{i + 1}.png")
    print(f"Wrote 14 scene thumbnails to {SCENES_DIR}")


if __name__ == "__main__":
    main()
