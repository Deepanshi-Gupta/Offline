"""Subtitle translation using Google MADLAD-400.

Provides the SubtitleTranslator class, which wraps the MADLAD-400
model loader to translate raw text, individual subtitle blocks, and
full lists of blocks (with batching support for throughput). MADLAD-400
is the production backend (Apache 2.0, commercially licensed); the
Meta NLLB-200 implementation (``nllb.py`` / ``nllb_loader.py``) is
retained separately and is used only for internal evaluation, not by
this class.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from translation_module.madlad_loader import MADLADModelLoader, get_madlad_translator
from translation_module.models import (
    EmptySubtitleError,
    LanguageDirection,
    SubtitleBlock,
    TranslationModuleError,
)
from translation_module.utils import (
    get_madlad_code,
    is_rtl_text,
    language_direction_from_madlad_code,
    normalize_text,
)

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 8
_DEFAULT_MAX_LENGTH = 512


class TranslationError(TranslationModuleError):
    """Raised when a translation operation fails."""


@dataclass(slots=True)
class TranslationResult:
    """Result of translating a single piece of text.

    Attributes:
        source_text: The original input text.
        translated_text: The translated output text.
        direction: Text directionality of the translated text.
    """

    source_text: str
    translated_text: str
    direction: LanguageDirection


class SubtitleTranslator:
    """Translates subtitle text and blocks using Google MADLAD-400.

    MADLAD-400 selects its output language via a ``"<2xx>"`` tag
    prepended to the source text rather than a forced BOS token, so
    unlike the retired NLLB-based translator this class does not need
    to resolve a target-language token id against the tokenizer's
    vocabulary.

    Attributes:
        source_language: Source language, as an ISO code (kept for API
            compatibility and logging; MADLAD-400 does not require an
            explicit source-language tag).
        target_language: Target language, resolved to a MADLAD-400
            ``"<2xx>"`` tag.
        batch_size: Number of texts translated per model forward pass.
        device: Compute device override (``"cuda"``, ``"mps"``, ``"cpu"``).
            When ``None``, the device is auto-detected by the model loader.
    """

    def __init__(
        self,
        source_language: str,
        target_language: str,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        device: Optional[str] = None,
        max_length: int = _DEFAULT_MAX_LENGTH,
        loader: Optional[MADLADModelLoader] = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        self.source_language = source_language
        self.target_language = get_madlad_code(target_language)
        self.batch_size = batch_size
        self.device = device
        self.max_length = max_length
        self._loader = loader or get_madlad_translator(device=device)

    def translate_text(self, text: str) -> str:
        """Translate a single string of text.

        Args:
            text: The text to translate. May be multiline.

        Returns:
            The translated text. Returns an empty string unchanged
            without invoking the model.

        Raises:
            TranslationError: If the model fails to produce a translation.
        """
        normalized = normalize_text(text)
        if not normalized:
            return ""

        results = self.batch_translate([normalized])
        return results[0]

    def translate_block(self, block: SubtitleBlock) -> SubtitleBlock:
        """Translate a single subtitle block, returning a new block.

        The original block's ``id``, ``start``, and ``end`` are preserved
        exactly; only ``translated_text`` is populated.

        Args:
            block: The subtitle block to translate.

        Returns:
            A new ``SubtitleBlock`` with ``translated_text`` populated.

        Raises:
            EmptySubtitleError: If the block's text is empty.
            TranslationError: If translation fails.
        """
        if not block.text.strip():
            raise EmptySubtitleError(f"Cannot translate empty block id={block.id}")

        translated = self.translate_text(block.text)
        return SubtitleBlock(
            id=block.id,
            start=block.start,
            end=block.end,
            text=block.text,
            translated_text=translated,
        )

    def translate_blocks(self, blocks: list[SubtitleBlock]) -> list[SubtitleBlock]:
        """Translate a list of subtitle blocks using batched inference.

        Empty blocks are skipped (returned unchanged with
        ``translated_text=None``) rather than raising, so a single bad
        block does not abort translation of an entire subtitle file.

        Args:
            blocks: Subtitle blocks to translate, in any order.

        Returns:
            New list of ``SubtitleBlock`` objects, same order and length
            as the input, with ``translated_text`` populated where
            translation succeeded.

        Raises:
            TranslationError: If the underlying model call fails.
        """
        if not blocks:
            return []

        translatable_indices: list[int] = []
        texts_to_translate: list[str] = []
        for i, block in enumerate(blocks):
            normalized = normalize_text(block.text)
            if normalized:
                translatable_indices.append(i)
                texts_to_translate.append(normalized)
            else:
                logger.warning("Skipping empty block id=%s during batch translation", block.id)

        translated_texts = self.batch_translate(texts_to_translate)

        result: list[SubtitleBlock] = list(blocks)
        for idx, translated in zip(translatable_indices, translated_texts):
            original = blocks[idx]
            result[idx] = SubtitleBlock(
                id=original.id,
                start=original.start,
                end=original.end,
                text=original.text,
                translated_text=translated,
            )
        return result

    def batch_translate(self, texts: list[str]) -> list[str]:
        """Translate a list of raw strings in batches.

        Args:
            texts: List of texts to translate. Empty strings are passed
                through unchanged (mapped to ``""``).

        Returns:
            List of translated strings, same order and length as input.

        Raises:
            TranslationError: If the model fails to generate a translation.
        """
        if not texts:
            return []

        try:
            import torch
        except ImportError as exc:
            raise TranslationError("torch is not installed") from exc

        tokenizer = self._loader.get_tokenizer()
        model = self._loader.get_model()
        device = self._loader.get_device()

        non_empty_indices = [i for i, t in enumerate(texts) if t.strip()]
        outputs: list[str] = ["" for _ in texts]

        if not non_empty_indices:
            return outputs

        try:
            for start in range(0, len(non_empty_indices), self.batch_size):
                batch_indices = non_empty_indices[start : start + self.batch_size]
                # MADLAD-400 selects the output language from a "<2xx>" tag
                # prepended to each source string, rather than a forced BOS
                # token id set on the generate() call.
                batch_texts = [f"{self.target_language} {texts[i]}" for i in batch_indices]

                encoded = tokenizer(
                    batch_texts,
                    return_tensors="pt",
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                ).to(device)

                with torch.no_grad():
                    generated_tokens = model.generate(
                        **encoded,
                        max_length=self.max_length,
                    )

                decoded = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)

                for i, translated in zip(batch_indices, decoded):
                    outputs[i] = translated.strip()

        except TranslationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise TranslationError(f"Batch translation failed: {exc}") from exc

        return outputs

    def get_target_direction(self) -> LanguageDirection:
        """Return the text direction of the configured target language."""
        return language_direction_from_madlad_code(self.target_language)

    def is_target_rtl_text(self, text: str) -> bool:
        """Check whether translated text is predominantly RTL script.

        Useful as a fallback/verification alongside
        ``get_target_direction()`` when the target language code alone
        is ambiguous (e.g. mixed-script content).

        Args:
            text: Text to inspect (typically translated output).

        Returns:
            ``True`` if the text is predominantly RTL script.
        """
        return is_rtl_text(text)