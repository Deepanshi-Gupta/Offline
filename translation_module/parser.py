"""Parsing and serialization of SRT and WebVTT subtitle files.

Reading is delegated to the well-tested ``pysrt`` and ``webvtt-py``
libraries for robustness against real-world file quirks, while writing
is implemented directly for precise control over formatting, numbering,
and timestamp fidelity.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import pysrt
import webvtt

from translation_module.models import (
    EmptySubtitleError,
    SubtitleBlock,
    SubtitleDocument,
    SubtitleFormat,
    SubtitleParsingError,
)
from translation_module.utils import (
    InvalidTimestampError,
    validate_srt_timestamp,
    validate_vtt_timestamp,
    write_text_file,
)

logger = logging.getLogger(__name__)

TextSelector = Callable[[SubtitleBlock], str]


def _default_text_selector(block: SubtitleBlock) -> str:
    """Default text selector: use the original subtitle text."""
    return block.text


def read_srt(path: Path) -> SubtitleDocument:
    """Read an SRT subtitle file.

    Args:
        path: Path to the ``.srt`` file.

    Returns:
        A ``SubtitleDocument`` containing the parsed blocks.

    Raises:
        SubtitleParsingError: If the file is missing or cannot be parsed,
            or contains a corrupt timestamp.
        EmptySubtitleError: If the file contains no usable subtitle blocks.
    """
    if not path.exists():
        raise SubtitleParsingError(f"SRT file not found: {path}")

    try:
        subs = pysrt.open(str(path), encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - re-raised as domain error
        raise SubtitleParsingError(f"Failed to parse SRT file {path}: {exc}") from exc

    blocks: list[SubtitleBlock] = []
    for item in subs:
        text = item.text.strip()
        if not text:
            logger.warning("Skipping empty SRT block (index=%s) in %s", item.index, path)
            continue

        start, end = str(item.start), str(item.end)
        try:
            validate_srt_timestamp(start)
            validate_srt_timestamp(end)
        except InvalidTimestampError as exc:
            raise SubtitleParsingError(f"Corrupt timestamp in {path}: {exc}") from exc

        blocks.append(SubtitleBlock(id=item.index, start=start, end=end, text=text))

    if not blocks:
        raise EmptySubtitleError(f"No valid subtitle blocks found in {path}")

    return SubtitleDocument(source_format=SubtitleFormat.SRT, blocks=blocks)


def read_vtt(path: Path) -> SubtitleDocument:
    """Read a WebVTT subtitle file.

    Args:
        path: Path to the ``.vtt`` file.

    Returns:
        A ``SubtitleDocument`` containing the parsed blocks.

    Raises:
        SubtitleParsingError: If the file is missing or cannot be parsed,
            or contains a corrupt timestamp.
        EmptySubtitleError: If the file contains no usable subtitle blocks.
    """
    if not path.exists():
        raise SubtitleParsingError(f"VTT file not found: {path}")

    try:
        captions = webvtt.read(str(path))
    except Exception as exc:  # noqa: BLE001 - re-raised as domain error
        raise SubtitleParsingError(f"Failed to parse VTT file {path}: {exc}") from exc

    blocks: list[SubtitleBlock] = []
    for index, caption in enumerate(captions, start=1):
        text = "\n".join(line.strip() for line in caption.lines if line.strip())
        if not text:
            logger.warning("Skipping empty VTT block (index=%s) in %s", index, path)
            continue

        start, end = caption.start, caption.end
        try:
            validate_vtt_timestamp(start)
            validate_vtt_timestamp(end)
        except InvalidTimestampError as exc:
            raise SubtitleParsingError(f"Corrupt timestamp in {path}: {exc}") from exc

        blocks.append(SubtitleBlock(id=index, start=start, end=end, text=text))

    if not blocks:
        raise EmptySubtitleError(f"No valid subtitle blocks found in {path}")

    return SubtitleDocument(source_format=SubtitleFormat.VTT, blocks=blocks)


def _validated_cues(
    blocks: Sequence[SubtitleBlock],
    text_selector: TextSelector,
    timestamp_validator: Callable[[str], None],
) -> list[tuple[int, str, str, str]]:
    """Validate and materialize cue data shared by both SRT and VTT writers.

    Args:
        blocks: Subtitle blocks to write.
        text_selector: Function extracting the text to write from a block.
        timestamp_validator: Format-specific timestamp validation function.

    Returns:
        A list of ``(id, start, end, text)`` tuples ready to render.

    Raises:
        EmptySubtitleError: If no blocks are provided, or a block's
            selected text is empty.
        InvalidTimestampError: If a block's start or end timestamp is malformed.
    """
    if not blocks:
        raise EmptySubtitleError("Cannot write a subtitle file with no blocks")

    cues: list[tuple[int, str, str, str]] = []
    for block in blocks:
        text = text_selector(block).strip()
        if not text:
            raise EmptySubtitleError(f"Empty subtitle text for block id={block.id}")

        timestamp_validator(block.start)
        timestamp_validator(block.end)
        cues.append((block.id, block.start, block.end, text))

    return cues


def write_srt(
    blocks: Sequence[SubtitleBlock],
    path: Path,
    text_selector: TextSelector = _default_text_selector,
) -> None:
    """Write subtitle blocks to an SRT file.

    Args:
        blocks: Subtitle blocks to write, in display order.
        path: Destination ``.srt`` file path.
        text_selector: Function selecting which text to render per block
            (defaults to the original ``text`` field). Pass a selector
            returning ``translated_text`` or merged dual-language text
            to produce other subtitle variants.

    Raises:
        EmptySubtitleError: If ``blocks`` is empty or a block has no text.
        InvalidTimestampError: If a timestamp is malformed.
    """
    cues = _validated_cues(blocks, text_selector, validate_srt_timestamp)

    entries = [f"{cue_id}\n{start} --> {end}\n{text}\n" for cue_id, start, end, text in cues]
    content = "\n".join(entries) + "\n"
    write_text_file(path, content)


def write_vtt(
    blocks: Sequence[SubtitleBlock],
    path: Path,
    text_selector: TextSelector = _default_text_selector,
) -> None:
    """Write subtitle blocks to a WebVTT file.

    Args:
        blocks: Subtitle blocks to write, in display order.
        path: Destination ``.vtt`` file path.
        text_selector: Function selecting which text to render per block
            (defaults to the original ``text`` field). Pass a selector
            returning ``translated_text`` or merged dual-language text
            to produce other subtitle variants.

    Raises:
        EmptySubtitleError: If ``blocks`` is empty or a block has no text.
        InvalidTimestampError: If a timestamp is malformed.
    """
    cues = _validated_cues(blocks, text_selector, validate_vtt_timestamp)

    lines: list[str] = ["WEBVTT", ""]
    for cue_id, start, end, text in cues:
        lines.append(str(cue_id))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")

    content = "\n".join(lines).rstrip("\n") + "\n"
    write_text_file(path, content)