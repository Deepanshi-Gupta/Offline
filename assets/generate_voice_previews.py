"""Generates short synthesized preview tones for the 12 voice-library entries.

There is no offline TTS model wired into this mockup, so each "preview" is a
distinct short tone pattern (pure stdlib: wave + math) rather than real speech.
It exists so the Voice / TTS screen has something real to play through
st.audio instead of a dead button.
"""

import math
import struct
import wave
from pathlib import Path

HERE = Path(__file__).parent
OUT_DIR = HERE / "voice_previews"

SAMPLE_RATE = 22050


def synth_tone(freqs, duration_each=0.28, sample_rate=SAMPLE_RATE):
    samples = []
    for freq in freqs:
        n = int(sample_rate * duration_each)
        for i in range(n):
            t = i / sample_rate
            # gentle attack/release envelope so tones don't click
            env = min(1.0, i / (n * 0.1), (n - i) / (n * 0.1))
            val = math.sin(2 * math.pi * freq * t) * 0.3 * env
            samples.append(val)
    return samples


def write_wav(path: Path, samples, sample_rate=SAMPLE_RATE):
    with wave.open(str(path), "w") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = b"".join(struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767)) for s in samples)
        wf.writeframes(frames)


# each voice gets a small 3-note motif at a different base pitch, purely so
# the 12 previews are audibly distinguishable from one another
BASE_NOTES = [220, 233, 247, 262, 277, 294, 311, 330, 349, 370, 392, 415]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for i, base in enumerate(BASE_NOTES, start=1):
        motif = [base, base * 1.25, base * 1.5]
        samples = synth_tone(motif)
        write_wav(OUT_DIR / f"voice_{i}.wav", samples)
    print(f"Wrote {len(BASE_NOTES)} voice preview tones to {OUT_DIR}")


if __name__ == "__main__":
    main()
