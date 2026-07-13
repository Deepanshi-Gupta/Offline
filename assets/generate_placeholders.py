"""Generates abstract placeholder portrait thumbnails so the UI demos run fully offline."""

from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
FACES_DIR = HERE / "faces"
REFS_DIR = HERE / "references"

SKIN_TONES = [
    (196, 154, 122),
    (224, 189, 155),
    (139, 98, 71),
    (232, 199, 168),
    (171, 128, 96),
    (110, 76, 58),
]

HAIR_TONES = [
    (35, 25, 20),
    (60, 42, 30),
    (20, 18, 16),
    (75, 50, 35),
    (25, 20, 18),
    (45, 32, 24),
]

BG_TONES = [
    (86, 90, 96),
    (94, 84, 78),
    (74, 78, 86),
    (98, 88, 82),
    (80, 84, 90),
    (70, 72, 78),
]

SIZE = (300, 300)


def draw_portrait(bg, skin, hair, size=SIZE):
    img = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(img)
    w, h = size

    # shoulders / torso
    draw.ellipse((w * 0.1, h * 0.62, w * 0.9, h * 1.25), fill=(45, 55, 70))

    # neck
    draw.rectangle((w * 0.42, h * 0.55, w * 0.58, h * 0.72), fill=skin)

    # head
    draw.ellipse((w * 0.28, h * 0.14, w * 0.72, h * 0.62), fill=skin)

    # hair (top cap)
    draw.pieslice((w * 0.26, h * 0.10, w * 0.74, h * 0.5), start=180, end=360, fill=hair)
    draw.rectangle((w * 0.26, h * 0.28, w * 0.74, h * 0.34), fill=hair)

    return img


def draw_face_placeholder(idx):
    bg = BG_TONES[idx % len(BG_TONES)]
    skin = SKIN_TONES[idx % len(SKIN_TONES)]
    hair = HAIR_TONES[idx % len(HAIR_TONES)]
    return draw_portrait(bg, skin, hair)


def draw_reference_placeholder(idx):
    # slightly cropped higher (head/hair only), matching the top-cropped
    # thumbnails in the "Ultra-realistic Image Generation" reference row.
    bg = BG_TONES[(idx + 2) % len(BG_TONES)]
    skin = SKIN_TONES[(idx + 3) % len(SKIN_TONES)]
    hair = HAIR_TONES[(idx + 1) % len(HAIR_TONES)]
    img = draw_portrait(bg, skin, hair, size=(300, 180))
    return img


def main():
    FACES_DIR.mkdir(parents=True, exist_ok=True)
    REFS_DIR.mkdir(parents=True, exist_ok=True)

    for i in range(1, 7):
        draw_face_placeholder(i).save(FACES_DIR / f"face_{i}.png")

    for i in range(1, 6):
        draw_reference_placeholder(i).save(REFS_DIR / f"ref_{i}.png")

    print(f"Wrote {len(list(FACES_DIR.glob('*.png')))} face images to {FACES_DIR}")
    print(f"Wrote {len(list(REFS_DIR.glob('*.png')))} reference images to {REFS_DIR}")


if __name__ == "__main__":
    main()
