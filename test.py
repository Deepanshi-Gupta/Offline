'''from pathlib import Path
from translation_module import read_srt, SubtitleTranslator, export_all_variants, SubtitleFormat

doc = read_srt(Path("input.srt"))
translator = SubtitleTranslator(source_language="en", target_language="ar")
translated = translator.translate_blocks(doc.blocks)
export_all_variants(translated, Path("output"), "input", SubtitleFormat.SRT)'''

from pathlib import Path
from translation_module import (
    read_srt,
    SubtitleTranslator,
    export_all_variants,
    SubtitleFormat,
)

doc = read_srt(Path("input.srt"))

languages = {
    "de": "German",
    "fr": "French",
    "tr": "Turkish",
    "es": "Spanish",
    "it": "Italian",
}

for lang_code, lang_name in languages.items():
    print(f"Translating to {lang_name}...")
    translator = SubtitleTranslator(source_language="en", target_language=lang_code)
    translated = translator.translate_blocks(doc.blocks)
    export_all_variants(translated, Path("output"), f"input.{lang_code}", SubtitleFormat.SRT)