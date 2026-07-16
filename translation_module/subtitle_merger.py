"""Subtitle merging utilities.

Produces original-only, translated-only, and dual-language variants of
a list of subtitle blocks, ready to be passed to ``exporter.py`` (or
``parser.write_srt`` / ``parser.write_vtt`` directly via a text
selector). Dual-language output supports configurable stacking order
and line separators.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Optional

from translation_module.models import EmptySubtitleError, SubtitleBlock

logger = logging.getLogger(__name__)


class SubtitleOrder(str, Enum):
    """Stacking order for dual-language subtitle lines."""

    ORIGINAL_TOP = "original_top"
    TRANSLATED_TOP = "translated_top"


class SubtitleSeparator(str, Enum):
    """Preset separators between original and translated lines."""

    NEWLINE = "newline"
    BLANK_LINE = "blank_line"


_SEPARATOR_VALUES: dict[SubtitleSeparator, str] = {
    SubtitleSeparator.NEWLINE: "\n",
    SubtitleSeparator.BLANK_LINE: "\n\n",
}


def _resolve_separator(separator: SubtitleSeparator | str) -> str:
    """Resolve a separator preset or custom string to its literal value.

    Args:
        separator: A ``SubtitleSeparator`` preset, or any custom string
            (e.g. ``" | "``) to use verbatim between lines.

    Returns:
        The literal separator string to join lines with.
    """
    if isinstance(separator, SubtitleSeparator):
        return _SEPARATOR_VALUES[separator]
    return separator


def get_original_text(block: SubtitleBlock) -> str:
    """Text selector returning a block's original text.

    Args:
        block: The subtitle block.

    Returns:
        The block's original ``text`` field.

    Raises:
        EmptySubtitleError: If the original text is empty.
    """
    if not block.text.strip():
        raise EmptySubtitleError(f"Block id={block.id} has no original text")
    return block.text


def get_translated_text(block: SubtitleBlock) -> str:
    """Text selector returning a block's translated text.

    Args:
        block: The subtitle block.

    Returns:
        The block's ``translated_text`` field.

    Raises:
        EmptySubtitleError: If the block has not been translated, or the
            translation is empty.
    """
    if not block.translated_text or not block.translated_text.strip():
        raise EmptySubtitleError(f"Block id={block.id} has no translated text")
    return block.translated_text


def get_dual_text(
    block: SubtitleBlock,
    order: SubtitleOrder = SubtitleOrder.ORIGINAL_TOP,
    separator: SubtitleSeparator | str = SubtitleSeparator.NEWLINE,
) -> str:
    """Text selector returning a block's combined original + translated text.

    Args:
        block: The subtitle block.
        order: Whether the original or translated line appears first.
        separator: A ``SubtitleSeparator`` preset or custom string placed
            between the two lines.

    Returns:
        The merged dual-language text for the block.

    Raises:
        EmptySubtitleError: If either the original or translated text
            is missing/empty.
    """
    original = get_original_text(block)
    translated = get_translated_text(block)
    sep = _resolve_separator(separator)

    if order == SubtitleOrder.ORIGINAL_TOP:
        return f"{original}{sep}{translated}"
    return f"{translated}{sep}{original}"


def merge_original_only(blocks: list[SubtitleBlock]) -> list[SubtitleBlock]:
    """Return blocks unchanged, validated to contain original text.

    Args:
        blocks: Subtitle blocks to validate.

    Returns:
        The same blocks, in the same order (new list, same objects).

    Raises:
        EmptySubtitleError: If ``blocks`` is empty or any block has no
            original text.
    """
    if not blocks:
        raise EmptySubtitleError("Cannot merge an empty list of blocks")
    for block in blocks:
        get_original_text(block)
    return list(blocks)


def merge_translated_only(blocks: list[SubtitleBlock]) -> list[SubtitleBlock]:
    """Return new blocks whose ``text`` is replaced by the translated text.

    Timestamps and ``id`` are preserved exactly; ``translated_text`` is
    carried over unchanged on the returned blocks.

    Args:
        blocks: Subtitle blocks with translations already populated.

    Returns:
        New list of ``SubtitleBlock`` objects with ``text`` set to the
        translated content.

    Raises:
        EmptySubtitleError: If ``blocks`` is empty or any block is
            missing a translation.
    """
    if not blocks:
        raise EmptySubtitleError("Cannot merge an empty list of blocks")

    result: list[SubtitleBlock] = []
    for block in blocks:
        translated = get_translated_text(block)
        result.append(
            SubtitleBlock(
                id=block.id,
                start=block.start,
                end=block.end,
                text=translated,
                translated_text=block.translated_text,
            )
        )
    return result


def merge_dual_language(
    blocks: list[SubtitleBlock],
    order: SubtitleOrder = SubtitleOrder.ORIGINAL_TOP,
    separator: SubtitleSeparator | str = SubtitleSeparator.NEWLINE,
) -> list[SubtitleBlock]:
    """Return new blocks whose ``text`` combines original and translated lines.

    Timestamps and ``id`` are preserved exactly.

    Args:
        blocks: Subtitle blocks with translations already populated.
        order: Whether the original or translated line appears first
            in each cue.
        separator: A ``SubtitleSeparator`` preset (newline / blank line)
            or a custom string to place between the two lines.

    Returns:
        New list of ``SubtitleBlock`` objects with ``text`` set to the
        merged dual-language content.

    Raises:
        EmptySubtitleError: If ``blocks`` is empty, or any block is
            missing original or translated text.
    """
    if not blocks:
        raise EmptySubtitleError("Cannot merge an empty list of blocks")

    result: list[SubtitleBlock] = []
    for block in blocks:
        dual_text = get_dual_text(block, order=order, separator=separator)
        result.append(
            SubtitleBlock(
                id=block.id,
                start=block.start,
                end=block.end,
                text=dual_text,
                translated_text=block.translated_text,
            )
        )
    return result