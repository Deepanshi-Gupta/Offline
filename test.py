from pathlib import Path
from translation_module import read_srt, SubtitleTranslator, export_all_variants, SubtitleFormat

doc = read_srt(Path("input.srt"))
translator = SubtitleTranslator(source_language="en", target_language="ar")
translated = translator.translate_blocks(doc.blocks)
export_all_variants(translated, Path("output"), "input", SubtitleFormat.SRT)