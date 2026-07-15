"""Static data for the Sound Library / Audio Layering screen (§7 of the UI
audit): the 16 FX categories from Hasaballa_Plan.pdf, a small representative
sample per category (the real spec wants 50+ per category — this is a mock),
and the per-asset religious-compliance flags (music / oud / tarab / neutral)
that drive the compliance-blocking demo.
"""

CATEGORIES = [
    "Emotional", "Military", "Tension", "Ambience", "City", "Nature", "Crowd",
    "Broadcast", "Chase", "Horses & Combat", "Religious", "Arab Cultural",
    "Era Ambiences", "Foley", "Weather", "Transitions",
]

# still being curated — an honest empty state, not a bug
EMPTY_CATEGORIES = {"Era Ambiences", "Horses & Combat", "Weather"}

ERAS = ["Contemporary", "1980s–90s", "Classical / Historic", "Future / Sci-fi"]
REGIONS = ["Gulf", "Levant", "Egypt", "Maghreb", "Global"]

FLAG_LABELS = {
    "music": ("Music", "#6E3AC0"),
    "oud": ("Oud", "#1A56DB"),
    "tarab": ("Tarab", "#0E8E7D"),
    "neutral": ("Neutral", "#6B6E76"),
}

# Each category lists (name, compliance_flag) pairs explicitly — the flag is
# picked to match what the name actually describes, not assigned positionally,
# so a sample named "Neutral Percussion" can never end up flagged "Music".
CATEGORY_ITEMS = {
    "Emotional": [("Heartfelt Swell", "music"), ("Melancholy Drone", "neutral"), ("Hopeful Rise", "neutral"), ("Grief Motif", "music")],
    "Military": [("Marching Drums", "neutral"), ("Radio Chatter Loop", "neutral"), ("Convoy Rumble", "neutral"), ("Salute Horn", "neutral")],
    "Tension": [("Rising Drone", "neutral"), ("Heartbeat Pulse", "neutral"), ("Sub Bass Hit", "neutral"), ("Creeping Strings", "music")],
    "Ambience": [("Room Tone", "neutral"), ("Wind Through Windows", "neutral"), ("Distant Traffic", "neutral"), ("Night Hum", "neutral")],
    "City": [("Street Bustle", "neutral"), ("Market Chatter", "neutral"), ("Traffic Pass-by", "neutral"), ("Construction Loop", "neutral")],
    "Nature": [("Forest Birds", "neutral"), ("River Flow", "neutral"), ("Wind in Trees", "neutral"), ("Desert Breeze", "neutral")],
    "Crowd": [("Applause Burst", "neutral"), ("Murmuring Crowd", "neutral"), ("Cheering Wave", "neutral"), ("Protest Chant", "neutral")],
    "Broadcast": [("News Stinger", "music"), ("TV Static", "neutral"), ("Radio Tune-in", "neutral"), ("Breaking Alert", "music")],
    "Chase": [("Footsteps Sprint", "neutral"), ("Engine Rev", "neutral"), ("Tires Screech", "neutral"), ("Heartbeat Chase", "neutral")],
    "Religious": [("Ambient Reverence Pad", "neutral"), ("Oud Reflection", "oud"), ("Tarab Interlude", "tarab"), ("Devotional Chant Backing", "music")],
    "Arab Cultural": [("Tarab Ensemble", "tarab"), ("Oud Solo", "oud"), ("Dabke Rhythm", "music"), ("Qanun Motif", "music")],
    "Foley": [("Door Creak", "neutral"), ("Footsteps — Wood", "neutral"), ("Cloth Rustle", "neutral"), ("Glass Clink", "neutral")],
    "Transitions": [("Whoosh Stinger", "neutral"), ("Riser Sting", "music"), ("Music Sting", "music"), ("Impact Hit", "neutral")],
}


def _build_assets():
    assets = []
    asset_id = 0
    for cat in CATEGORIES:
        if cat in EMPTY_CATEGORIES:
            continue
        for name, flag in CATEGORY_ITEMS[cat]:
            assets.append(
                {
                    "id": asset_id,
                    "name": name,
                    "category": cat,
                    "era": ERAS[asset_id % len(ERAS)],
                    "region": REGIONS[asset_id % len(REGIONS)],
                    "flag": flag,
                }
            )
            asset_id += 1
    return assets


ASSETS = _build_assets()


def assets_in_category(category: str):
    return [a for a in ASSETS if a["category"] == category]


def flag_badge_html(flag: str) -> str:
    label, color = FLAG_LABELS.get(flag, ("Neutral", "#6B6E76"))
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:0.78rem;'
        f'font-weight:700;color:{color};background:{color}1A;border-radius:999px;padding:2px 10px;">'
        f"{label}</span>"
    )
