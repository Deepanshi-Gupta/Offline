"""Subtitle translation with an NLLB-200 primary and MADLAD-400 fallback.

Provides the :class:`SubtitleTranslator` class, which translates raw
text, individual subtitle blocks, and full lists of blocks (with
batching for throughput).

Backend strategy:

* **Primary — Meta NLLB-200** (``nllb_loader.py``). Fast (600M distilled),
  loads from a local ``./models/nllb`` checkpoint when present, and
  produces the high-quality output used in evaluation. NLLB selects its
  output language by setting ``tokenizer.src_lang`` and forcing the
  target-language BOS token id on ``generate()``.
* **Fallback — Google MADLAD-400** (``madlad_loader.py``). Only loaded
  and invoked if the NLLB path raises (load failure, unsupported
  direction, or a generation error). MADLAD selects its output language
  via a ``"<2xx>"`` tag prepended to the source text instead of a forced
  BOS token, so it needs no target-token id lookup.

Both backends decode with beam search plus repetition penalties
(``num_beams`` / ``no_repeat_ngram_size`` / ``repetition_penalty``);
without these, large seq2seq models degenerate into repeated-token
output (dates, dots, single tokens repeated to the length limit).
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
from translation_module.nllb_loader import NLLBModelLoader, get_translator
from translation_module.utils import (
    get_madlad_code,
    get_nllb_code,
    is_rtl_text,
    language_direction_from_nllb_code,
    normalize_text,
)

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 8
_DEFAULT_MAX_LENGTH = 512

# Shared decoding settings. Greedy decoding on NLLB/MADLAD-sized models
# collapses into repeated-token garbage; beam search plus these repetition
# guards keep output well-formed.
_NUM_BEAMS = 4
_NO_REPEAT_NGRAM_SIZE = 3
_REPETITION_PENALTY = 1.1


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
    """Translates subtitle text and blocks, NLLB-200 first, MADLAD-400 as fallback.

    A single translation call tries the NLLB backend for the whole batch;
    if that raises for any reason it transparently retries the same batch
    on the MADLAD backend. The MADLAD model is constructed lazily, so its
    large checkpoint is never loaded unless the fallback is actually
    exercised.

    Attributes:
        source_language: Source language ISO code, resolved to an NLLB
            FLORES-200 code for the primary backend.
        target_language: Target language ISO code (kept raw; resolved
            separately per backend).
        batch_size: Number of texts translated per model forward pass.
        device: Compute device override (``"cuda"``, ``"mps"``, ``"cpu"``).
            When ``None``, the device is auto-detected by each loader.
    """

    def __init__(
        self,
        source_language: str,
        target_language: str,
        batch_size: int = _DEFAULT_BATCH_SIZE,
        device: Optional[str] = None,
        max_length: int = _DEFAULT_MAX_LENGTH,
        loader: Optional[NLLBModelLoader] = None,
        fallback_loader: Optional[MADLADModelLoader] = None,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        self.source_language = source_language
        self.target_language = target_language
        self.batch_size = batch_size
        self.device = device
        self.max_length = max_length

        # Primary backend language codes (NLLB / FLORES-200).
        self._nllb_src = get_nllb_code(source_language)
        self._nllb_tgt = get_nllb_code(target_language)
        # Fallback backend target tag (MADLAD "<2xx>").
        self._madlad_tgt = get_madlad_code(target_language)

        # Both loaders are lazy: constructing them does not load a model.
        # MADLAD only actually loads if the NLLB path fails at run time.
        self._primary = loader or get_translator(device=device)
        self._fallback = fallback_loader or get_madlad_translator(device=device)

    def translate_text(self, text: str) -> str:
        """Translate a single string of text.

        Args:
            text: The text to translate. May be multiline.

        Returns:
            The translated text. Returns an empty string unchanged
            without invoking the model.

        Raises:
            TranslationError: If both backends fail to produce a translation.
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

        Tries the NLLB primary backend for the whole batch; on any failure
        (model load error, unsupported direction, generation error) it logs
        the reason and retries the same batch on the MADLAD fallback.

        Args:
            texts: List of texts to translate. Empty strings are passed
                through unchanged (mapped to ``""``).

        Returns:
            List of translated strings, same order and length as input.

        Raises:
            TranslationError: If both the primary and fallback backends fail.
        """
        if not texts:
            return []

        non_empty_indices = [i for i, t in enumerate(texts) if t.strip()]
        outputs: list[str] = ["" for _ in texts]
        if not non_empty_indices:
            return outputs

        try:
            self._run_backend(self._primary, "nllb", texts, non_empty_indices, outputs)
            return outputs
        except Exception as primary_exc:  # noqa: BLE001 - fall back on any primary failure
            logger.warning(
                "NLLB primary backend failed (%s); falling back to MADLAD-400",
                primary_exc,
            )

        # Reset any partial primary output before the fallback pass.
        outputs = ["" for _ in texts]
        try:
            self._run_backend(self._fallback, "madlad", texts, non_empty_indices, outputs)
            return outputs
        except Exception as fallback_exc:  # noqa: BLE001
            raise TranslationError(
                f"Both NLLB and MADLAD backends failed: {fallback_exc}"
            ) from fallback_exc

    def _run_backend(
        self,
        loader,  # noqa: ANN001 - NLLBModelLoader | MADLADModelLoader, duck-typed
        backend: str,
        texts: list[str],
        non_empty_indices: list[int],
        outputs: list[str],
    ) -> None:
        """Translate ``non_empty_indices`` of ``texts`` in place into ``outputs``.

        ``backend`` selects how the output language is expressed: ``"nllb"``
        sets ``tokenizer.src_lang`` and forces the target BOS token id;
        ``"madlad"`` prepends the ``"<2xx>"`` target tag to each source
        string. Both decode with the shared beam-search/repetition settings.
        """
        try:
            import torch
        except ImportError as exc:
            raise TranslationError("torch is not installed") from exc

        tokenizer = loader.get_tokenizer()
        model = loader.get_model()
        device = loader.get_device()

        forced_bos_token_id: Optional[int] = None
        if backend == "nllb":
            # NLLB conditions on the source language set on the tokenizer and
            # a forced target-language BOS token id passed to generate().
            tokenizer.src_lang = self._nllb_src
            forced_bos_token_id = tokenizer.convert_tokens_to_ids(self._nllb_tgt)

        for start in range(0, len(non_empty_indices), self.batch_size):
            batch_indices = non_empty_indices[start : start + self.batch_size]

            if backend == "madlad":
                # MADLAD selects the output language from a "<2xx>" tag
                # prepended to each source string.
                batch_texts = [f"{self._madlad_tgt} {texts[i]}" for i in batch_indices]
            else:
                batch_texts = [texts[i] for i in batch_indices]

            encoded = tokenizer(
                batch_texts,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=self.max_length,
            ).to(device)

            generate_kwargs = {
                "max_length": self.max_length,
                "num_beams": _NUM_BEAMS,
                "no_repeat_ngram_size": _NO_REPEAT_NGRAM_SIZE,
                "repetition_penalty": _REPETITION_PENALTY,
            }
            if forced_bos_token_id is not None:
                generate_kwargs["forced_bos_token_id"] = forced_bos_token_id

            with torch.no_grad():
                generated_tokens = model.generate(**encoded, **generate_kwargs)

            decoded = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)
            for i, translated in zip(batch_indices, decoded):
                outputs[i] = translated.strip()

    def get_target_direction(self) -> LanguageDirection:
        """Return the text direction of the configured target language."""
        return language_direction_from_nllb_code(self._nllb_tgt)

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
