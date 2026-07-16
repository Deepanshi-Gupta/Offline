"""Subtitle export orchestration.

Provides a single high-level API for writing original, translated, or
dual-language subtitle variants to disk in SRT or VTT format, built on
top of ``parser.py`` (file writing) and ``subtitle_merger.py``
(variant generation).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from translation_module.models import (
    SubtitleBlock,
    SubtitleExportError,
    SubtitleFormat,
)
from translation_module.parser import write_srt, write_vtt
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

logger = logging.getLogger(__name__)

_WRITERS = {
    SubtitleFormat.SRT: write_srt,
    SubtitleFormat.VTT: write_vtt,
}


def _write(
    blocks: list[SubtitleBlock],
    path: Path,
    fmt: SubtitleFormat,
    text_selector,  # noqa: ANN001 - TextSelector type from parser.py
) -> None:
    """Dispatch to the correct format writer with unified error handling.

    Args:
        blocks: Subtitle blocks to write.
        path: Destination file path.
        fmt: Target subtitle format.
        text_selector: Function selecting which text field to render.

    Raises:
        SubtitleExportError: If writing fails for any reason.
    """
    writer = _WRITERS.get(fmt)
    if writer is None:
        raise SubtitleExportError(f"Unsupported export format: {fmt!r}")

    try:
        writer(blocks, path, text_selector=text_selector)
    except SubtitleExportError:
        raise
    except Exception as exc:  # noqa: BLE001 - wrap any writer failure
        raise SubtitleExportError(f"Failed to export {fmt.value.upper()} to {path}: {exc}") from exc

    logger.info("Exported %s subtitles (%d blocks) to %s", fmt.value.upper(), len(blocks), path)


def export_original(
    blocks: list[SubtitleBlock],
    path: Path,
    fmt: SubtitleFormat,
) -> None:
    """Export the original (untranslated) subtitles.

    Args:
        blocks: Subtitle blocks to export.
        path: Destination file path.
        fmt: Target subtitle format (SRT or VTT).

    Raises:
        EmptySubtitleError: If ``blocks`` is empty or any block has no
            original text.
        InvalidTimestampError: If a block's timestamp is malformed.
        SubtitleExportError: If writing to disk fails.
    """
    validated = merge_original_only(blocks)
    _write(validated, path, fmt, get_original_text)


def export_translated(
    blocks: list[SubtitleBlock],
    path: Path,
    fmt: SubtitleFormat,
) -> None:
    """Export the translated subtitles only.

    Args:
        blocks: Subtitle blocks, each with ``translated_text`` populated.
        path: Destination file path.
        fmt: Target subtitle format (SRT or VTT).

    Raises:
        EmptySubtitleError: If ``blocks`` is empty or any block is
            missing a translation.
        InvalidTimestampError: If a block's timestamp is malformed.
        SubtitleExportError: If writing to disk fails.
    """
    merged = merge_translated_only(blocks)
    _write(merged, path, fmt, get_translated_text)


def export_dual_language(
    blocks: list[SubtitleBlock],
    path: Path,
    fmt: SubtitleFormat,
    order: SubtitleOrder = SubtitleOrder.ORIGINAL_TOP,
    separator: SubtitleSeparator | str = SubtitleSeparator.NEWLINE,
) -> None:
    """Export dual-language subtitles (original + translated per cue).

    Args:
        blocks: Subtitle blocks, each with ``translated_text`` populated.
        path: Destination file path.
        fmt: Target subtitle format (SRT or VTT).
        order: Whether the original or translated line appears first
            in each cue.
        separator: A ``SubtitleSeparator`` preset or custom string
            placed between the original and translated lines.

    Raises:
        EmptySubtitleError: If ``blocks`` is empty or any block is
            missing original or translated text.
        InvalidTimestampError: If a block's timestamp is malformed.
        SubtitleExportError: If writing to disk fails.
    """
    merged = merge_dual_language(blocks, order=order, separator=separator)
    text_selector = lambda block: block.text  # noqa: E731 - merged blocks already hold final text
    _write(merged, path, fmt, text_selector)


def export_all_variants(
    blocks: list[SubtitleBlock],
    output_dir: Path,
    base_name: str,
    fmt: SubtitleFormat,
    order: SubtitleOrder = SubtitleOrder.ORIGINAL_TOP,
    separator: SubtitleSeparator | str = SubtitleSeparator.NEWLINE,
    include_original: bool = True,
    include_translated: bool = True,
    include_dual: bool = True,
) -> dict[str, Path]:
    """Export any combination of original, translated, and dual-language files.

    Files are named ``{base_name}.{variant}.{ext}``, e.g.
    ``movie.original.srt``, ``movie.translated.srt``, ``movie.dual.srt``.

    Args:
        blocks: Subtitle blocks, each with ``translated_text`` populated
            (unless ``include_translated`` and ``include_dual`` are both
            ``False``).
        output_dir: Directory to write files into. Created if missing.
        base_name: Filename stem shared by all exported variants.
        fmt: Target subtitle format (SRT or VTT).
        order: Stacking order used for the dual-language variant.
        separator: Separator used for the dual-language variant.
        include_original: Whether to export the original-only variant.
        include_translated: Whether to export the translated-only variant.
        include_dual: Whether to export the dual-language variant.

    Returns:
        A mapping of variant name (``"original"``, ``"translated"``,
        ``"dual"``) to the path it was written to, for each variant
        that was requested.

    Raises:
        ValueError: If no variant is selected for export.
        EmptySubtitleError: If ``blocks`` is empty or missing required text.
        InvalidTimestampError: If a block's timestamp is malformed.
        SubtitleExportError: If writing to disk fails.
    """
    if not (include_original or include_translated or include_dual):
        raise ValueError("At least one variant must be selected for export")

    output_dir.mkdir(parents=True, exist_ok=True)
    ext = fmt.value
    results: dict[str, Path] = {}

    if include_original:
        path = output_dir / f"{base_name}.original.{ext}"
        export_original(blocks, path, fmt)
        results["original"] = path

    if include_translated:
        path = output_dir / f"{base_name}.translated.{ext}"
        export_translated(blocks, path, fmt)
        results["translated"] = path

    if include_dual:
        path = output_dir / f"{base_name}.dual.{ext}"
        export_dual_language(blocks, path, fmt, order=order, separator=separator)
        results["dual"] = path

    return results