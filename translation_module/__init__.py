"""Hasaballa Translation Module.

Offline subtitle translation built on Google MADLAD-400 (production
backend, Apache 2.0 / commercially licensed). Reads SRT/VTT subtitles,
translates them, and exports original, translated, or dual-language
subtitle files.

The Meta NLLB-200 implementation (``nllb.py`` / ``nllb_loader.py``) is
still importable but is isolated from this production pipeline: it is
not used by ``SubtitleTranslator`` and is kept around only for internal
evaluation/comparison work.

Typical usage::

    from pathlib import Path
    from translation_module import (
        read_srt,
        SubtitleTranslator,
        export_all_variants,
        SubtitleFormat,
    )

    document = read_srt(Path("input.srt"))
    translator = SubtitleTranslator(source_language="en", target_language="ar")
    translated_blocks = translator.translate_blocks(document.blocks)

    export_all_variants(
        translated_blocks,
        output_dir=Path("output"),
        base_name="input",
        fmt=SubtitleFormat.SRT,
    )
"""

from translation_module.exporter import (
    export_all_variants,
    export_dual_language,
    export_original,
    export_translated,
)
from translation_module.models import (
    EmptySubtitleError,
    InvalidTimestampError,
    LanguageDirection,
    ModelLoadError,
    SubtitleBlock,
    SubtitleDocument,
    SubtitleExportError,
    SubtitleFormat,
    SubtitleParsingError,
    TranslationModuleError,
    UnsupportedLanguageError,
)
from translation_module.madlad_loader import MADLADModelLoader, get_madlad_translator
from translation_module.nllb_loader import NLLBModelLoader, get_translator
from translation_module.parser import read_srt, read_vtt, write_srt, write_vtt
from translation_module.subtitle_merger import (
    SubtitleOrder,
    SubtitleSeparator,
    get_dual_text,
    get_original_text,
    get_translated_text,
    merge_dual_language,
    merge_original_only,
    merge_translated_only,
)
from translation_module.translator import (
    SubtitleTranslator,
    TranslationError,
    TranslationResult,
)

__all__ = [
    # models
    "SubtitleBlock",
    "SubtitleDocument",
    "SubtitleFormat",
    "LanguageDirection",
    "TranslationModuleError",
    "SubtitleParsingError",
    "InvalidTimestampError",
    "EmptySubtitleError",
    "UnsupportedLanguageError",
    "ModelLoadError",
    "SubtitleExportError",
    # parser
    "read_srt",
    "read_vtt",
    "write_srt",
    "write_vtt",
    # madlad_loader (production backend)
    "MADLADModelLoader",
    "get_madlad_translator",
    # nllb_loader (internal evaluation only; not used by SubtitleTranslator)
    "NLLBModelLoader",
    "get_translator",
    # translator
    "SubtitleTranslator",
    "TranslationResult",
    "TranslationError",
    # subtitle_merger
    "SubtitleOrder",
    "SubtitleSeparator",
    "get_original_text",
    "get_translated_text",
    "get_dual_text",
    "merge_original_only",
    "merge_translated_only",
    "merge_dual_language",
    # exporter
    "export_original",
    "export_translated",
    "export_dual_language",
    "export_all_variants",
]

__version__ = "1.0.0"