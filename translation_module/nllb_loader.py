"""Singleton loader for the Meta NLLB-200 translation model.

Lazily loads and caches the HuggingFace model and tokenizer, and
automatically selects the best available compute device (CUDA, then
Apple Silicon MPS, falling back to CPU). Designed to be imported and
used as a module-level singleton via ``get_translator()``.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

from translation_module.models import ModelLoadError

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_NAME = "facebook/nllb-200-distilled-600M"


class NLLBModelLoader:
    """Thread-safe singleton that lazily loads the NLLB model and tokenizer.

    Attributes:
        model_name: HuggingFace model identifier or local path.
        device: Resolved torch device string (``"cuda"``, ``"mps"`` or
            ``"cpu"``), determined on first load unless overridden.
    """

    _instance: Optional["NLLBModelLoader"] = None
    _instance_lock = threading.Lock()

    def __new__(cls, *args: object, **kwargs: object) -> "NLLBModelLoader":
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
        """Load the NLLB model and tokenizer into memory if not already loaded.

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
            logger.info("Loading NLLB model %r on device %r", self.model_name, self.device)

            try:
                tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name)
                model.to(self.device)
                model.eval()
            except Exception as exc:  # noqa: BLE001 - wrap any loading failure
                raise ModelLoadError(
                    f"Failed to load NLLB model {self.model_name!r}: {exc}"
                ) from exc

            self._tokenizer = tokenizer
            self._model = model
            logger.info("NLLB model loaded successfully on %r", self.device)

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


def get_translator(
    model_name: str = _DEFAULT_MODEL_NAME,
    device: Optional[str] = None,
) -> NLLBModelLoader:
    """Get the singleton :class:`NLLBModelLoader` instance.

    Args:
        model_name: HuggingFace model identifier or local path. Only
            applied the first time the singleton is constructed.
        device: Optional device override (e.g. ``"cuda"``, ``"cpu"``).
            Only applied the first time the singleton is constructed.

    Returns:
        The shared :class:`NLLBModelLoader` instance.
    """
    return NLLBModelLoader(model_name=model_name, device=device)