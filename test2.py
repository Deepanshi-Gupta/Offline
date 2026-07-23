from pathlib import Path
from translation_module import (
    read_srt,
    read_vtt,
    SubtitleTranslator,
    export_original,
    export_translated,
    export_dual_language,
    SubtitleFormat,
    EmptySubtitleError,
    SubtitleParsingError,
    InvalidTimestampError,
)

test_data_dir = Path("test_data")
output_dir = Path("output")
output_dir.mkdir(exist_ok=True)

# Map each test file to its reader, format, and the language its text is
# actually written in. The source language must match the file's real
# content: NLLB (the primary backend) encodes the input using this code,
# so mislabeling Arabic text as English produces bad translations.
test_files = {
    "arabic.srt": (read_srt, SubtitleFormat.SRT, "ar"),
    "empty.srt": (read_srt, SubtitleFormat.SRT, "en"),
    "english.srt": (read_srt, SubtitleFormat.SRT, "en"),
    "english.vtt": (read_vtt, SubtitleFormat.VTT, "en"),
    "long.srt": (read_srt, SubtitleFormat.SRT, "en"),
    "mixed.srt": (read_srt, SubtitleFormat.SRT, "en"),
    "multiline.srt": (read_srt, SubtitleFormat.SRT, "en"),
    "special.srt": (read_srt, SubtitleFormat.SRT, "en"),
}

languages = {
    "de": "German",
    "fr": "French",
    "tr": "Turkish",
    "es": "Spanish",
    "it": "Italian",
}

for filename, (reader, fmt, source_lang) in test_files.items():
    file_path = test_data_dir / filename
    stem = file_path.stem  # e.g. "arabic", "empty"

    print(f"\n=== Testing {filename} ===")

    # --- Parse ---
    try:
        doc = reader(file_path)
        print(f"  Parsed OK: {len(doc.blocks)} blocks")
    except EmptySubtitleError as exc:
        print(f"  Expected empty-file error: {exc}")
        continue
    except SubtitleParsingError as exc:
        print(f"  Parsing failed: {exc}")
        continue
    except InvalidTimestampError as exc:
        print(f"  Bad timestamp: {exc}")
        continue

    # --- Export original (once per file) ---
    try:
        export_original(doc.blocks, output_dir / f"{stem}.original.{fmt.value}", fmt)
    except Exception as exc:  # noqa: BLE001 - surface any export issue during testing
        print(f"  Original export failed: {exc}")
        continue

    # --- Translate + export translated/dual per language ---
    for lang_code, lang_name in languages.items():
        try:
            translator = SubtitleTranslator(source_language=source_lang, target_language=lang_code)
            translated = translator.translate_blocks(doc.blocks)

            export_translated(
                translated, output_dir / f"{stem}.{lang_code}.translated.{fmt.value}", fmt
            )
            export_dual_language(
                translated, output_dir / f"{stem}.{lang_code}.dual.{fmt.value}", fmt
            )
            print(f"  {lang_name}: OK")
        except Exception as exc:  # noqa: BLE001 - keep testing remaining languages/files
            print(f"  {lang_name} failed: {exc}")

print("\nDone.")