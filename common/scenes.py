"""Path helper for the offline scene-batch placeholder thumbnails."""

from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets"


def scene_paths():
    return sorted(
        (ASSETS_DIR / "scenes").glob("scene_*.png"),
        key=lambda p: int(p.stem.split("_")[1]),
    )
