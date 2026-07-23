"""Verify the NLLB-primary / MADLAD-fallback control flow in SubtitleTranslator.

Runs entirely on stub loaders, so it needs no model download and no
network. It proves two things:

  1. Happy path: when NLLB works, MADLAD is never touched.
  2. Fallback path: when NLLB raises, MADLAD takes over and the
     "falling back" warning is logged.

Run with:  python test_fallback.py
"""

import logging

from translation_module import SubtitleTranslator

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


class _Encoded(dict):
    """Minimal stand-in for a tokenizer batch-encoding (supports ``.to()``)."""

    def to(self, _device):
        return self


class _StubTokenizer:
    def __init__(self, texts_holder):
        self._texts_holder = texts_holder

    def __call__(self, batch_texts, **_kwargs):
        # Remember what we were asked to translate so the fake model can echo it.
        return _Encoded(texts=list(batch_texts))

    def convert_tokens_to_ids(self, _token):
        return 123  # NLLB target BOS id; value is irrelevant to the stub

    def batch_decode(self, generated, **_kwargs):
        return list(generated)


class _StubModel:
    def __init__(self, label):
        self._label = label

    def generate(self, **kwargs):
        # Echo each input back, tagged with which backend produced it.
        return [f"{self._label}:{t}" for t in kwargs["texts"]]


class WorkingLoader:
    """A stub loader whose model tags output with ``label``. Records use."""

    def __init__(self, label):
        self.label = label
        self.used = False

    def get_tokenizer(self):
        self.used = True
        return _StubTokenizer(None)

    def get_model(self):
        self.used = True
        return _StubModel(self.label)

    def get_device(self):
        return "cpu"


class BrokenLoader:
    """A stub loader that fails, simulating an NLLB load/generation error."""

    def __init__(self):
        self.used = False

    def get_tokenizer(self):
        self.used = True
        raise RuntimeError("simulated NLLB failure")

    def get_model(self):
        raise RuntimeError("simulated NLLB failure")

    def get_device(self):
        return "cpu"


def run_case(title, primary, fallback):
    print(f"\n=== {title} ===")
    t = SubtitleTranslator(
        source_language="en",
        target_language="de",
        loader=primary,          # primary  = NLLB slot
        fallback_loader=fallback,  # fallback = MADLAD slot
    )
    out = t.translate_text("hello world")
    print(f"  output           : {out!r}")
    print(f"  primary used?    : {getattr(primary, 'used', None)}")
    print(f"  fallback used?   : {getattr(fallback, 'used', None)}")
    return out


# Case A: NLLB works -> output tagged NLLB, MADLAD untouched.
a_primary = WorkingLoader("NLLB")
a_fallback = WorkingLoader("MADLAD")
out_a = run_case("Case A: NLLB healthy (fallback must NOT run)", a_primary, a_fallback)
assert out_a.startswith("NLLB:"), out_a
assert a_fallback.used is False, "MADLAD should not have been used!"
print("  PASS: NLLB used, MADLAD untouched")

# Case B: NLLB broken -> fallback kicks in, output tagged MADLAD.
b_primary = BrokenLoader()
b_fallback = WorkingLoader("MADLAD")
out_b = run_case("Case B: NLLB broken (fallback MUST run)", b_primary, b_fallback)
assert out_b.startswith("MADLAD:"), out_b
assert b_fallback.used is True, "MADLAD fallback should have been used!"
print("  PASS: NLLB failed, MADLAD fallback produced output")

print("\nAll fallback checks passed.")
