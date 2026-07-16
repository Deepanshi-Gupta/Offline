from pathlib import Path
from translation_module import (
    read_srt,
    SubtitleTranslator,
    export_original,
    export_translated,
    export_dual_language,
    SubtitleFormat,
)

doc = read_srt(Path("input.srt"))
output_dir = Path("output")

# 1. Original file — exported once, no translation needed
export_original(doc.blocks, output_dir / "input.original.srt", SubtitleFormat.SRT)

# 2. Translated + dual files — one pair per language
languages = {
    "de": "German",
    "fr": "French",
    "tr": "Turkish",
    "es": "Spanish",
    "it": "Italian",
    "en": "English",  # remove this line if English IS your source and doesn't need translating
}

for lang_code, lang_name in languages.items():
    print(f"Translating to {lang_name}...")
    translator = SubtitleTranslator(source_language="en", target_language=lang_code)
    translated = translator.translate_blocks(doc.blocks)

    export_translated(translated, output_dir / f"input.{lang_code}.translated.srt", SubtitleFormat.SRT)
    export_dual_language(translated, output_dir / f"input.{lang_code}.dual.srt", SubtitleFormat.SRT)