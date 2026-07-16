"""Domain models for the translation module.

Defines the core data structures (subtitle blocks), enumerations used
throughout the module (subtitle formats, language direction), and the
custom exception hierarchy raised by other components of this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SubtitleFormat(str, Enum):
    """Supported subtitle file formats."""

    SRT = "srt"
    VTT = "vtt"


class LanguageDirection(str, Enum):
    """Text directionality for a given language.

    Used to decide rendering/ordering behavior (e.g. RTL languages such
    as Arabic or Hebrew) when producing translated or dual-language
    subtitles.
    """

    LTR = "ltr"
    RTL = "rtl"


@dataclass(slots=True)
class SubtitleBlock:
    """A single subtitle entry (cue).

    Attributes:
        id: Sequential index of the subtitle block, starting at 1.
        start: Start timestamp, preserved exactly as parsed
            (e.g. "00:00:01,000" for SRT or "00:00:01.000" for VTT).
        end: End timestamp, preserved exactly as parsed.
        text: Original subtitle text. May contain multiple lines
            joined by "\\n".
        translated_text: Translated subtitle text, populated after
            running the block through the translator. ``None`` until
            translation has occurred.
    """

    id: int
    start: str
    end: str
    text: str
    translated_text: Optional[str] = None


@dataclass(slots=True)
class SubtitleDocument:
    """A parsed subtitle file: its format plus an ordered list of blocks.

    Attributes:
        source_format: The format the document was parsed from.
        blocks: Ordered list of subtitle blocks contained in the file.
    """

    source_format: SubtitleFormat
    blocks: list[SubtitleBlock] = field(default_factory=list)


class TranslationModuleError(Exception):
    """Base exception for all errors raised by the translation module."""


class SubtitleParsingError(TranslationModuleError):
    """Raised when a subtitle file cannot be parsed."""


class InvalidTimestampError(TranslationModuleError):
    """Raised when a subtitle timestamp is malformed or corrupt."""


class EmptySubtitleError(TranslationModuleError):
    """Raised when a subtitle file or block contains no usable text."""


class UnsupportedLanguageError(TranslationModuleError):
    """Raised when a requested language code is not supported by NLLB."""


class ModelLoadError(TranslationModuleError):
    """Raised when the NLLB model or tokenizer fails to load."""


class SubtitleExportError(TranslationModuleError):
    """Raised when writing a subtitle file fails."""