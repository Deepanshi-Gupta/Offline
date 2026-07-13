"""Static data for the Voice/TTS screen: the 12-voice library and 21-dialect
list from Hasaballa_Plan.pdf §5, plus a path helper for the offline preview
tones. Quality ratings are illustrative placeholders standing in for the
"transparent dialect quality" requirement — real ratings would come from the
actual TTS/dialect team.
"""

from pathlib import Path

ASSETS_DIR = Path(__file__).parent.parent / "assets"

QUALITY_COLORS = {
    "high": "#22B35E",
    "medium": "#E3A008",
    "low": "#E2622A",
    "unsupported": "#9AA0A6",
}
QUALITY_LABELS = {
    "high": "High quality",
    "medium": "Medium quality",
    "low": "Low quality",
    "unsupported": "Preview unavailable",
}

# The 12 named voice types from the client's actual §7-G spec: "A full voice
# library — in Arabic (all dialects) & English — used when no reference audio
# is provided." use_case = the client's "Suitable for ..." line, best_for =
# the client's "Best/Great/Good for ..." dialect-suitability line.
VOICES = [
    {
        "name": "Male Deep",
        "icon": "🎙️",
        "use_case": "Modern Standard Arabic / Formal English — Narration, News, Trailer",
        "best_for": "Arabic MSA, Formal tone (not dialectal)",
        "quality": "high",
    },
    {
        "name": "Male Youthful",
        "icon": "🎬",
        "use_case": "Dialects / casual English — Dialogue, Social Media",
        "best_for": "Egyptian, Levantine, Gulf, Maghrebi dialects — casual, youth content",
        "quality": "high",
    },
    {
        "name": "Male Senior",
        "icon": "🧓",
        "use_case": "Storytelling / documentaries — Storytelling, History",
        "best_for": "Arabic storytelling tone — can adapt to dialects with tuning",
        "quality": "high",
    },
    {
        "name": "Female Warm",
        "icon": "☀️",
        "use_case": "Calm Modern Standard Arabic / educational English — Podcast, Explainer",
        "best_for": "Arabic MSA, soft narration — neutral or classic",
        "quality": "high",
    },
    {
        "name": "Female Energetic",
        "icon": "📣",
        "use_case": "Ads / promo in dialects or English — Promo, Ads",
        "best_for": "Egyptian, Gulf, Levantine — high-energy content",
        "quality": "high",
    },
    {
        "name": "Female Expressive",
        "icon": "🎭",
        "use_case": "Dramatic dialogues / theatrical performance — Drama, Character",
        "best_for": "All dialects depending on emotion — great for dramatization",
        "quality": "high",
    },
    {
        "name": "Youth Voice",
        "icon": "🧒",
        "use_case": "Content targeting kids or teens in Arabic/English — Cartoons, Games",
        "best_for": "All Arabic dialects depending on context (kids, youth)",
        "quality": "high",
    },
    {
        "name": "Neutral Educator",
        "icon": "🏫",
        "use_case": "Lessons and tutorials — E-Learning, Tutorials",
        "best_for": "Arabic MSA or simplified dialects — formal learning tone",
        "quality": "high",
    },
    {
        "name": "Corporate Neutral",
        "icon": "💼",
        "use_case": "Formal presentations / corporate training — Corporate, Training",
        "best_for": "MSA or Gulf-style formal speech — serious tone",
        "quality": "high",
    },
    {
        "name": "Storyteller Calm",
        "icon": "🌄",
        "use_case": "Podcasts and stories in both languages — Podcast, Audiobook",
        "best_for": "Soft dialectal storytelling (Egyptian, Levantine, etc.)",
        "quality": "high",
    },
    {
        "name": "Singing-Ready Voice (Male)",
        "icon": "🎶",
        "use_case": "Capable of singing in Arabic or English",
        "best_for": "Adaptable to any dialect for music/dubbing — needs tuning",
        "quality": "high",
    },
    {
        "name": "Singing-Ready Voice (Female)",
        "icon": "🎶",
        "use_case": "Capable of singing in Arabic or English",
        "best_for": "Adaptable to any dialect for music/dubbing — needs tuning",
        "quality": "high",
    },
]

# name, arabic name, quality
DIALECTS = [
    {"name": "Modern Standard Arabic (MSA)", "ar": "الفصحى", "quality": "high"},
    {"name": "Egyptian (Masri)", "ar": "المصرية", "quality": "high"},
    {"name": "Gulf / Khaleeji", "ar": "الخليجية", "quality": "high"},
    {"name": "Saudi (Najdi)", "ar": "النجدية", "quality": "high"},
    {"name": "Hijazi", "ar": "الحجازية", "quality": "medium"},
    {"name": "Levantine (Shami)", "ar": "الشامية", "quality": "high"},
    {"name": "Syrian", "ar": "السورية", "quality": "high"},
    {"name": "Lebanese", "ar": "اللبنانية", "quality": "high"},
    {"name": "Jordanian", "ar": "الأردنية", "quality": "medium"},
    {"name": "Palestinian", "ar": "الفلسطينية", "quality": "medium"},
    {"name": "Iraqi", "ar": "العراقية", "quality": "high"},
    {"name": "Kuwaiti", "ar": "الكويتية", "quality": "medium"},
    {"name": "Emirati", "ar": "الإماراتية", "quality": "medium"},
    {"name": "Qatari", "ar": "القطرية", "quality": "medium"},
    {"name": "Bahraini", "ar": "البحرينية", "quality": "low"},
    {"name": "Omani", "ar": "العمانية", "quality": "low"},
    {"name": "Yemeni", "ar": "اليمنية", "quality": "low"},
    {"name": "Moroccan (Darija)", "ar": "الدارجة المغربية", "quality": "medium"},
    {"name": "Algerian", "ar": "الجزائرية", "quality": "low"},
    {"name": "Tunisian", "ar": "التونسية", "quality": "low"},
    {"name": "Libyan", "ar": "الليبية", "quality": "unsupported"},
]

SPEED_PRESETS = {"Slow": 0.75, "Normal": 1.0, "Fast": 1.35, "Sprint": 1.75}


def voice_preview_path(idx: int) -> Path:
    return ASSETS_DIR / "voice_previews" / f"voice_{idx + 1}.wav"


def quality_badge_html(quality: str) -> str:
    color = QUALITY_COLORS.get(quality, "#9AA0A6")
    label = QUALITY_LABELS.get(quality, quality)
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;font-size:0.8rem;color:#46484E;">'
        f'<span style="width:9px;height:9px;border-radius:50%;background:{color};display:inline-block;"></span>'
        f"{label}</span>"
    )
