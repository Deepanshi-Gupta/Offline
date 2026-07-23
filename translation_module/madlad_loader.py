"""Singleton loader for Google's MADLAD-400 translation model.

MADLAD-400 is the production translation backend: it is released
under Apache 2.0 (commercially licensed, unlike NLLB-200's CC-BY-NC
research license) and is the model actually used to translate
subtitles. It follows the same lazy-load, thread-safe singleton
pattern as ``nllb_loader.py`` (which is retained separately, and only
used for internal, non-production evaluation).

MADLAD-400 is a single-tokenizer, target-tag-conditioned T5 model: the
desired output language is selected by prepending a ``"<2xx>"`` tag to
the source text (see ``utils.get_madlad_code``) rather than by setting
a source language and a forced BOS token id, as NLLB requires.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

from translation_module.models import ModelLoadError

logger = logging.getLogger(__name__)

# 3B is the smallest MADLAD-400 finetuned checkpoint that still covers
# all 400+ languages at production quality; swap for the 7B/10B variant
# via the `model_name` constructor argument if more quality headroom
# (at the cost of latency/memory) is needed.
_DEFAULT_MODEL_NAME = "google/madlad400-3b-mt"

# Preferred local checkpoint directory, mirroring the NLLB loader. When this
# folder exists it is loaded instead of pulling the multi-gigabyte 3B model
# from the HuggingFace hub on first use; if absent, loading falls back to the
# hub identifier in ``model_name``.
_LOCAL_MODEL_DIR = Path("models") / "madlad"


def _resolve_model_source(model_name: str) -> str:
    """Return a local checkpoint path if available, else the hub identifier.

    Only substitutes the local directory when the caller left
    ``model_name`` at its default; an explicitly supplied path/id is
    always honored as-is.
    """
    if model_name == _DEFAULT_MODEL_NAME and _LOCAL_MODEL_DIR.is_dir():
        return str(_LOCAL_MODEL_DIR)
    return model_name


class MADLADModelLoader:
    """Thread-safe singleton that lazily loads the MADLAD-400 model and tokenizer.

    Attributes:
        model_name: HuggingFace model identifier or local path.
        device: Resolved torch device string (``"cuda"``, ``"mps"`` or
            ``"cpu"``), determined on first load unless overridden.
    """

    _instance: Optional["MADLADModelLoader"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args: object, **kwargs: object) -> "MADLADModelLoader":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        model_name: str = _DEFAULT_MODEL_NAME,
        device: Optional[str] = None,
    ) -> None:
        if self._initialized:
            return
        self.model_name = model_name
        self._requested_device = device
        self.device: Optional[str] = None
        self._model = None
        self._tokenizer = None
        self._load_lock = threading.Lock()
        self._initialized = True

    def _resolve_device(self) -> str:
        """Detect the best available compute device.

        Returns:
            ``"cuda"`` if a CUDA GPU is available, ``"mps"`` if running
            on Apple Silicon with MPS support, otherwise ``"cpu"``.
        """
        if self._requested_device:
            return self._requested_device

        try:
            import torch
        except ImportError as exc:
            raise ModelLoadError("torch is not installed") from exc

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            return "mps"
        return "cpu"

    def load_model(self) -> None:
        """Load the MADLAD-400 model and tokenizer into memory if not already loaded.

        Thread-safe and idempotent: concurrent callers block until the
        first caller finishes loading, then reuse the cached instance.

        Raises:
            ModelLoadError: If the model or tokenizer fails to load.
        """
        if self._model is not None and self._tokenizer is not None:
            return

        with self._load_lock:
            if self._model is not None and self._tokenizer is not None:
                return

            try:
                import torch
                from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            except ImportError as exc:
                raise ModelLoadError(
                    "Required packages 'torch' and 'transformers' must be installed"
                ) from exc

            self.device = self._resolve_device()
            source = _resolve_model_source(self.model_name)
            logger.info(
                "Loading MADLAD-400 model %r (from %r) on device %r",
                self.model_name,
                source,
                self.device,
            )

            try:
                tokenizer = AutoTokenizer.from_pretrained(source)
                model = AutoModelForSeq2SeqLM.from_pretrained(source)
                model.to(self.device)
                model.eval()
            except Exception as exc:  # noqa: BLE001 - wrap any loading failure
                raise ModelLoadError(
                    f"Failed to load MADLAD-400 model {self.model_name!r}: {exc}"
                ) from exc

            self._tokenizer = tokenizer
            self._model = model
            logger.info("MADLAD-400 model loaded successfully on %r", self.device)

    def get_model(self):  # noqa: ANN201 - transformers model type not imported at module scope
        """Return the cached model, loading it first if necessary."""
        self.load_model()
        return self._model

    def get_tokenizer(self):  # noqa: ANN201 - transformers tokenizer type not imported at module scope
        """Return the cached tokenizer, loading it first if necessary."""
        self.load_model()
        return self._tokenizer

    def get_device(self) -> str:
        """Return the resolved compute device, loading the model first if necessary."""
        self.load_model()
        assert self.device is not None
        return self.device

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton instance (primarily for testing purposes)."""
        with cls._instance_lock:
            cls._instance = None


def get_madlad_translator(
    model_name: str = _DEFAULT_MODEL_NAME,
    device: Optional[str] = None,
) -> MADLADModelLoader:
    """Get the singleton :class:`MADLADModelLoader` instance.

    Args:
        model_name: HuggingFace model identifier or local path. Only
            applied the first time the singleton is constructed.
        device: Optional device override (e.g. ``"cuda"``, ``"cpu"``).
            Only applied the first time the singleton is constructed.

    Returns:
        The shared :class:`MADLADModelLoader` instance.
    """
    return MADLADModelLoader(model_name=model_name, device=device)