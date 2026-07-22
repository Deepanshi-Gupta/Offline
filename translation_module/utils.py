"""Utility helpers shared across the translation module.

Includes SRT/VTT timestamp validation and conversion, language code
mapping to MADLAD-400's target-language tags (production) and NLLB's
FLORES-200 codes (retained only for the isolated internal-evaluation
path), text normalization, RTL script detection, and small
file-encoding helpers.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from pathlib import Path

from translation_module.models import (
    InvalidTimestampError,
    LanguageDirection,
    UnsupportedLanguageError,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Timestamp handling
# ---------------------------------------------------------------------------

_SRT_TIMESTAMP_RE = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3}$")
_VTT_TIMESTAMP_RE = re.compile(r"^(\d{2}:)?\d{2}:\d{2}\.\d{3}$")


def validate_srt_timestamp(timestamp: str) -> None:
    """Validate an SRT timestamp of the form ``HH:MM:SS,mmm``.

    Args:
        timestamp: The timestamp string to validate.

    Raises:
        InvalidTimestampError: If the timestamp is malformed.
    """
    if not _SRT_TIMESTAMP_RE.match(timestamp):
        raise InvalidTimestampError(f"Invalid SRT timestamp: {timestamp!r}")
    _validate_time_components(timestamp.replace(",", ":"))


def validate_vtt_timestamp(timestamp: str) -> None:
    """Validate a WebVTT timestamp of the form ``HH:MM:SS.mmm`` or ``MM:SS.mmm``.

    Args:
        timestamp: The timestamp string to validate.

    Raises:
        InvalidTimestampError: If the timestamp is malformed.
    """
    if not _VTT_TIMESTAMP_RE.match(timestamp):
        raise InvalidTimestampError(f"Invalid VTT timestamp: {timestamp!r}")
    _validate_time_components(timestamp.replace(".", ":"))


def _validate_time_components(colon_separated: str) -> None:
    """Validate that hours/minutes/seconds/ms fall within sane ranges.

    Args:
        colon_separated: Timestamp with all separators normalized to ``:``.

    Raises:
        InvalidTimestampError: If any component is out of range.
    """
    parts = colon_separated.split(":")
    if len(parts) == 4:
        hours, minutes, seconds, millis = (int(p) for p in parts)
    elif len(parts) == 3:
        hours = 0
        minutes, seconds, millis = (int(p) for p in parts)
    else:
        raise InvalidTimestampError(f"Invalid timestamp components: {colon_separated!r}")

    if minutes >= 60 or seconds >= 60 or millis >= 1000 or hours < 0:
        raise InvalidTimestampError(
            f"Timestamp component out of range: {colon_separated!r}"
        )


def srt_timestamp_to_ms(timestamp: str) -> int:
    """Convert an SRT timestamp to total milliseconds.

    Args:
        timestamp: A valid SRT timestamp (``HH:MM:SS,mmm``).

    Returns:
        Total number of milliseconds represented by the timestamp.

    Raises:
        InvalidTimestampError: If the timestamp is malformed.
    """
    validate_srt_timestamp(timestamp)
    hms, millis = timestamp.split(",")
    hours, minutes, seconds = (int(p) for p in hms.split(":"))
    return (((hours * 60 + minutes) * 60) + seconds) * 1000 + int(millis)


def ms_to_srt_timestamp(total_ms: int) -> str:
    """Convert total milliseconds to an SRT timestamp string.

    Args:
        total_ms: Total number of milliseconds (must be >= 0).

    Returns:
        A timestamp formatted as ``HH:MM:SS,mmm``.

    Raises:
        InvalidTimestampError: If ``total_ms`` is negative.
    """
    if total_ms < 0:
        raise InvalidTimestampError(f"Negative duration not allowed: {total_ms}")
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def ms_to_vtt_timestamp(total_ms: int) -> str:
    """Convert total milliseconds to a WebVTT timestamp string.

    Args:
        total_ms: Total number of milliseconds (must be >= 0).

    Returns:
        A timestamp formatted as ``HH:MM:SS.mmm``.

    Raises:
        InvalidTimestampError: If ``total_ms`` is negative.
    """
    return ms_to_srt_timestamp(total_ms).replace(",", ".")


def srt_to_vtt_timestamp(timestamp: str) -> str:
    """Convert an SRT timestamp to WebVTT format.

    Args:
        timestamp: A valid SRT timestamp (``HH:MM:SS,mmm``).

    Returns:
        The equivalent WebVTT timestamp (``HH:MM:SS.mmm``).
    """
    validate_srt_timestamp(timestamp)
    return timestamp.replace(",", ".")


def vtt_to_srt_timestamp(timestamp: str) -> str:
    """Convert a WebVTT timestamp to SRT format.

    Args:
        timestamp: A valid WebVTT timestamp.

    Returns:
        The equivalent SRT timestamp (``HH:MM:SS,mmm``), zero-padding
        hours if the source omitted them.
    """
    validate_vtt_timestamp(timestamp)
    hms, millis = timestamp.split(".")
    if hms.count(":") == 1:
        hms = f"00:{hms}"
    return f"{hms},{millis}"


# ---------------------------------------------------------------------------
# Language mapping (ISO 639-1 / common codes -> NLLB FLORES-200 codes)
# ---------------------------------------------------------------------------

_ISO_TO_NLLB: dict[str, str] = {
    "en": "eng_Latn",
    "ar": "arb_Arab",
    "fr": "fra_Latn",
    "de": "deu_Latn",
    "es": "spa_Latn",
    "it": "ita_Latn",
    "pt": "por_Latn",
    "ru": "rus_Cyrl",
    "zh": "zho_Hans",
    "zh-tw": "zho_Hant",
    "ja": "jpn_Jpan",
    "ko": "kor_Hang",
    "hi": "hin_Deva",
    "ur": "urd_Arab",
    "he": "heb_Hebr",
    "fa": "pes_Arab",
    "tr": "tur_Latn",
    "nl": "nld_Latn",
    "pl": "pol_Latn",
    "sv": "swe_Latn",
    "id": "ind_Latn",
    "vi": "vie_Latn",
    "th": "tha_Thai",
    "el": "ell_Grek",
    "uk": "ukr_Cyrl",
    "bn": "ben_Beng",
    "ta": "tam_Taml",
    "sw": "swh_Latn",
}

# Scripts (FLORES-200 suffix) that are written right-to-left.
_RTL_SCRIPTS: frozenset[str] = frozenset({"Arab", "Hebr", "Nkoo", "Thaa", "Adlm"})


def get_nllb_code(language: str) -> str:
    """Resolve a language code to its NLLB FLORES-200 identifier.

    Accepts either a plain ISO 639-1 code (e.g. ``"en"``) or an
    already-valid FLORES-200 code (e.g. ``"eng_Latn"``), which is
    returned unchanged.

    Args:
        language: Language identifier supplied by the caller.

    Returns:
        The corresponding FLORES-200 language code.

    Raises:
        UnsupportedLanguageError: If the language cannot be resolved.
    """
    normalized = language.strip()
    if re.match(r"^[a-z]{3}_[A-Z][a-z]{3}$", normalized):
        return normalized

    code = _ISO_TO_NLLB.get(normalized.lower())
    if code is None:
        raise UnsupportedLanguageError(f"Unsupported language code: {language!r}")
    return code


def language_direction_from_nllb_code(nllb_code: str) -> LanguageDirection:
    """Determine text direction from a FLORES-200 language code.

    Args:
        nllb_code: A FLORES-200 code such as ``"arb_Arab"``.

    Returns:
        ``LanguageDirection.RTL`` if the code's script is right-to-left,
        otherwise ``LanguageDirection.LTR``.
    """
    script = nllb_code.split("_")[-1] if "_" in nllb_code else ""
    return LanguageDirection.RTL if script in _RTL_SCRIPTS else LanguageDirection.LTR


# ---------------------------------------------------------------------------
# Language mapping (ISO 639-1 / common codes -> MADLAD-400 target tags)
# ---------------------------------------------------------------------------

# MADLAD-400 conditions generation on a bare target-language code wrapped
# in a "<2xx>" tag prepended to the source text (e.g. "<2de>"). Most codes
# match ISO 639-1 directly; a handful of MADLAD's codes diverge from the
# "obvious" ISO code, which is why an explicit table is used instead of
# passing the caller's code straight through.
_ISO_TO_MADLAD: dict[str, str] = {
    "en": "en",
    "ar": "ar",
    "fr": "fr",
    "de": "de",
    "es": "es",
    "it": "it",
    "pt": "pt",
    "ru": "ru",
    "zh": "zh",
    "zh-tw": "zh-Latn",  # MADLAD has no dedicated Traditional-script tag
    "ja": "ja",
    "ko": "ko",
    "hi": "hi",
    "ur": "ur",
    "he": "iw",  # MADLAD (like older Google products) uses the legacy code
    "fa": "fa",
    "tr": "tr",
    "nl": "nl",
    "pl": "pl",
    "sv": "sv",
    "id": "id",
    "vi": "vi",
    "th": "th",
    "el": "el",
    "uk": "uk",
    "bn": "bn",
    "ta": "ta",
    "sw": "sw",
}

_MADLAD_TAG_RE = re.compile(r"^<2[a-zA-Z-]+>$")


def get_madlad_code(language: str) -> str:
    """Resolve a language code to its MADLAD-400 target-language tag.

    Accepts a plain ISO 639-1 code (e.g. ``"en"``), a bare MADLAD code
    that isn't in the ISO table (returned as ``"<2{code}>"``), or an
    already-formed ``"<2xx>"`` tag, which is returned unchanged.

    Args:
        language: Language identifier supplied by the caller.

    Returns:
        The corresponding MADLAD-400 tag, e.g. ``"<2de>"``.

    Raises:
        UnsupportedLanguageError: If the language cannot be resolved.
    """
    normalized = language.strip()
    if _MADLAD_TAG_RE.match(normalized):
        return normalized

    code = _ISO_TO_MADLAD.get(normalized.lower())
    if code is None:
        raise UnsupportedLanguageError(f"Unsupported language code: {language!r}")
    return f"<2{code}>"


# Bare MADLAD language codes (i.e. without the "<2...>" wrapper) that are
# written right-to-left. Unlike FLORES-200, MADLAD tags carry no script
# suffix, so direction has to be looked up by code instead of parsed.
_MADLAD_RTL_CODES: frozenset[str] = frozenset({"ar", "iw", "ur", "fa", "ps", "sd", "ug", "yi"})


def language_direction_from_madlad_code(madlad_tag: str) -> LanguageDirection:
    """Determine text direction from a MADLAD-400 target-language tag.

    Args:
        madlad_tag: A MADLAD tag such as ``"<2ar>"``.

    Returns:
        ``LanguageDirection.RTL`` if the language is right-to-left,
        otherwise ``LanguageDirection.LTR``.
    """
    code = madlad_tag.strip("<>").lstrip("2")
    return LanguageDirection.RTL if code in _MADLAD_RTL_CODES else LanguageDirection.LTR


# ---------------------------------------------------------------------------
# Text normalization and RTL detection
# ---------------------------------------------------------------------------

_RTL_UNICODE_RANGES = (
    (0x0590, 0x05FF),  # Hebrew
    (0x0600, 0x06FF),  # Arabic
    (0x0700, 0x074F),  # Syriac
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB1D, 0xFDFF),  # Hebrew/Arabic presentation forms
    (0xFE70, 0xFEFF),  # Arabic presentation forms-B
)


def normalize_text(text: str) -> str:
    """Normalize subtitle text for translation.

    Applies Unicode NFC normalization, collapses redundant internal
    whitespace on each line, and strips leading/trailing whitespace
    while preserving intentional line breaks.

    Args:
        text: Raw subtitle text, possibly multiline.

    Returns:
        The normalized text.
    """
    lines = text.splitlines()
    normalized_lines = [
        unicodedata.normalize("NFC", re.sub(r"[ \t]+", " ", line)).strip()
        for line in lines
    ]
    return "\n".join(normalized_lines).strip()


def is_rtl_text(text: str) -> bool:
    """Detect whether text is predominantly right-to-left script.

    Args:
        text: The text to inspect.

    Returns:
        ``True`` if RTL characters form the majority of the
        directional (letter) characters in the text.
    """
    rtl_count = 0
    directional_count = 0
    for char in text:
        code_point = ord(char)
        if not char.isalpha():
            continue
        directional_count += 1
        if any(start <= code_point <= end for start, end in _RTL_UNICODE_RANGES):
            rtl_count += 1
    if directional_count == 0:
        return False
    return rtl_count / directional_count > 0.5


# ---------------------------------------------------------------------------
# Encoding helpers
# ---------------------------------------------------------------------------


def read_text_file(path: Path, encoding: str = "utf-8") -> str:
    """Read a text file, falling back to ``utf-8-sig`` if a BOM is present.

    Args:
        path: Path to the file to read.
        encoding: Preferred encoding to try first.

    Returns:
        The decoded file contents.
    """
    raw_bytes = path.read_bytes()
    if raw_bytes.startswith(b"\xef\xbb\xbf"):
        return raw_bytes.decode("utf-8-sig")
    return raw_bytes.decode(encoding)


def write_text_file(path: Path, content: str, encoding: str = "utf-8") -> None:
    """Write text content to a file, creating parent directories as needed.

    Args:
        path: Destination file path.
        content: Text content to write.
        encoding: Encoding to use when writing.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding, newline="\n")