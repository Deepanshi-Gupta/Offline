"""Tiny offline audio helpers shared by the voice-cloning mockup.

No TTS model is wired in here — "generated"/"cloned" audio and voice-library
previews are all short synthesized tones (stdlib wave/math only), just enough
to give the UI something real to play and draw a waveform from.
"""

import io
import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 22050


def synth_tone(freqs, duration_each=0.28, sample_rate=SAMPLE_RATE):
    samples = []
    for freq in freqs:
        n = int(sample_rate * duration_each)
        for i in range(n):
            t = i / sample_rate
            env = min(1.0, i / (n * 0.1), (n - i) / (n * 0.1))
            val = math.sin(2 * math.pi * freq * t) * 0.3 * env
            samples.append(val)
    return samples


def samples_to_wav_bytes(samples, sample_rate=SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples)
        wf.writeframes(frames)
    return buf.getvalue()


def load_wav_samples(path: Path):
    with wave.open(str(path), "r") as wf:
        n = wf.getnframes()
        raw = wf.readframes(n)
        return [s / 32768.0 for s in struct.unpack(f"<{n}h", raw)]


def waveform_svg_data_uri(samples, width=560, height=56, color="#2F6FEF") -> str:
    """Renders a bar-style amplitude envelope as an inline SVG data URI."""
    import base64

    if not samples:
        samples = [0.0]
    bars = 64
    chunk = max(1, len(samples) // bars)
    levels = []
    for i in range(bars):
        chunk_samples = samples[i * chunk : (i + 1) * chunk] or [0.0]
        levels.append(max(abs(s) for s in chunk_samples))
    peak = max(levels) or 1.0
    levels = [lvl / peak for lvl in levels]

    bar_w = width / bars
    mid = height / 2
    rects = []
    for i, lvl in enumerate(levels):
        h = max(2, lvl * (height - 6))
        x = i * bar_w
        y = mid - h / 2
        rects.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.6:.1f}" height="{h:.1f}" rx="1.5" fill="{color}" />')

    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">{"".join(rects)}</svg>'
    )
    encoded = base64.b64encode(svg.encode()).decode()
    return f"data:image/svg+xml;base64,{encoded}"
