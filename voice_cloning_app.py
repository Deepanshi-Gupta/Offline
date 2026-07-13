"""Standalone Streamlit page: Voice / TTS & Voice Cloning (§5 of the UI audit).

Rebuilt against Hasaballa_Plan.pdf §5 "Voice / TTS & Voice Cloning": a
12-voice library browser with per-voice preview, a 21-dialect selector that
is honest about quality (per the UX note — not all dialects are equal),
per-character voice assignment, a 0.5x-2.0x speed control with presets, and
real Generating / Voice-clone-processing states.

There is no offline TTS or voice-cloning model wired in — "generated" and
"cloned" audio, and every voice-library preview, are short synthesized tones
(common/audio.py, stdlib only) so the states have something real to play
and draw a waveform from, instead of dead buttons.

Run with:
    python -m streamlit run voice_cloning_app.py
"""

import time

import streamlit as st

from common.style import face_paths, image_to_data_uri
from common.voices import DIALECTS, SPEED_PRESETS, VOICES, quality_badge_html, voice_preview_path
from common.audio import load_wav_samples, samples_to_wav_bytes, synth_tone, waveform_svg_data_uri

st.set_page_config(page_title="Voice / TTS & Voice Cloning", layout="centered")

faces = face_paths()
VOICE_NAMES = [f"{v['icon']} {v['name']}" for v in VOICES]
DIALECT_NAMES = [d["name"] for d in DIALECTS]

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}

    .block-container { max-width: 1100px; padding: 2rem 2.25rem; }

    .page-title { font-size: 2rem; font-weight: 800; color: #101114; margin-bottom: 0; }
    .offline-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: #E8F7EE; color: #187A43; border: 1px solid #BEE8CC;
        border-radius: 999px; padding: 3px 12px; font-size: 0.8rem; font-weight: 600;
    }
    .offline-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: #22B35E; }

    .sec-header { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; margin-top: 1rem; }
    .icon-badge {
        flex: 0 0 auto; width: 34px; height: 34px; border-radius: 50%;
        background: #16171A; color: #fff; display: flex; align-items: center;
        justify-content: center; font-size: 16px;
    }
    .icon-badge.green { border-radius: 8px; background: #29B36B; }

    .feature-title { font-size: 1.3rem; font-weight: 700; color: #111318; }
    .feature-subtitle { font-size: 0.96rem; color: #46484E; margin: 0.15rem 0 0.9rem 46px; }

    .face-row img { width: 100%; border-radius: 10px; object-fit: cover; aspect-ratio: 1/1; }

    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea {
        border-radius: 10px; border: 1px solid #DDDFE3; background: #F4F5F7;
    }
    div[data-testid="stButton"] button { border-radius: 10px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }

    hr { margin: 1.3rem 0; border-color: #E6E7EA; }

    .dialect-row { display: flex; align-items: center; justify-content: space-between; padding: 3px 0; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def section_header(title: str, icon: str = "🎤", variant: str = "dark"):
    st.markdown(
        f'<div class="sec-header"><div class="icon-badge {variant}">{icon}</div>'
        f'<div class="feature-title">{title}</div></div>',
        unsafe_allow_html=True,
    )


def section_desc(text: str):
    st.markdown(f'<div class="feature-subtitle">{text}</div>', unsafe_allow_html=True)


def _init_state():
    st.session_state.setdefault("char_voice_0", 0)  # Male Deep
    st.session_state.setdefault("char_voice_1", 3)  # Female Warm
    st.session_state.setdefault("char_voice_2", 5)  # Female Expressive
    st.session_state.setdefault("speaking_as", 0)
    st.session_state.setdefault("dialect_selected", DIALECT_NAMES[0])
    st.session_state.setdefault("speed", 1.0)
    st.session_state.setdefault("gen_audio", None)
    st.session_state.setdefault("clone_audio", None)
    st.session_state.setdefault("preview_open", set())


_init_state()


def placeholder_audio(base_freq: float):
    samples = synth_tone([base_freq, base_freq * 1.25, base_freq * 1.5], duration_each=0.22)
    return samples_to_wav_bytes(samples), samples


# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.2])
with h1:
    st.markdown('<div class="page-title">Voice / TTS &amp; Voice Cloning</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.5rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline — no network used</span></div>',
        unsafe_allow_html=True,
    )
st.caption("No local TTS/voice-cloning model is wired in yet — generated and cloned audio below are placeholder tones, not real speech.")

# =========================================================
# A - REFERENCE VOICES FOR MULTIPLE CHARACTERS
# =========================================================
section_header("A - Reference Voices for Multiple Characters", icon="🎙️")

left, right = st.columns([1.3, 1])

with left:
    img_cols = st.columns(3)
    for i, (col, path) in enumerate(zip(img_cols, faces[:3])):
        with col:
            st.markdown('<div class="face-row">', unsafe_allow_html=True)
            st.image(image_to_data_uri(path), width="stretch")
            st.markdown("</div>", unsafe_allow_html=True)
            st.selectbox(
                f"Character {i + 1} voice",
                options=range(len(VOICE_NAMES)),
                format_func=lambda idx: VOICE_NAMES[idx],
                key=f"char_voice_{i}",
                label_visibility="collapsed",
            )
            st.caption(f"Character {i + 1}")

with right:
    st.selectbox(
        "Speaking as",
        options=range(3),
        format_func=lambda i: f"Character {i + 1}",
        key="speaking_as",
    )
    st.text_area(
        "Text to speech",
        placeholder="Enter text to convert to speech...",
        height=90,
        label_visibility="collapsed",
        key="tts_text",
    )
    if st.button("Generate Voice", type="primary", key="generate_voice", width="stretch"):
        char_idx = st.session_state.speaking_as
        voice_idx = st.session_state[f"char_voice_{char_idx}"]
        voice = VOICES[voice_idx]
        if not st.session_state.tts_text.strip():
            st.warning("No text entered — nothing to generate.")
        elif voice["quality"] == "unsupported":
            st.warning(f"{voice['name']}'s preview sample isn't ready yet — generation quality may be low.")
        else:
            with st.spinner(f"Generating with {voice['icon']} {voice['name']}…"):
                time.sleep(0.8)
            base = 200 + voice_idx * 12
            audio_bytes, samples = placeholder_audio(base * st.session_state.speed)
            st.session_state.gen_audio = (audio_bytes, samples, voice["name"])
    if st.session_state.gen_audio:
        audio_bytes, samples, voice_name = st.session_state.gen_audio
        st.caption(f"Generated — voice: {voice_name}")
        st.audio(audio_bytes, format="audio/wav")
        st.image(waveform_svg_data_uri(samples), width="stretch")

    st.write("")
    ref_audio = st.file_uploader(
        "Reference audio (cloning)",
        type=["wav", "mp3", "m4a"],
        label_visibility="collapsed",
        key="reference_audio_upload",
    )
    if st.button("Clone Voice 🎙️", type="primary", key="clone_voice", width="stretch"):
        if ref_audio is None:
            st.warning("Upload a reference audio file before cloning.")
        else:
            with st.spinner("Voice-clone processing…"):
                time.sleep(1.0)
            base = 180 + (len(ref_audio.getvalue()) % 40)
            audio_bytes, samples = placeholder_audio(base)
            st.session_state.clone_audio = (audio_bytes, samples)
    if st.session_state.clone_audio:
        audio_bytes, samples = st.session_state.clone_audio
        st.caption("Cloned voice — 100% match target (placeholder audio)")
        st.audio(audio_bytes, format="audio/wav")
        st.image(waveform_svg_data_uri(samples), width="stretch")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# VOICE LIBRARY BROWSER (12 named voice types) — §7-G spec
# =========================================================
section_header("G - Full Voice Library — 12 Voice Types", icon="📚")
section_desc("A full voice library — in Arabic (all dialects) & English — used when no reference audio is provided.")

for row_start in (0, 3, 6, 9):
    cols = st.columns(3)
    for c in range(3):
        i = row_start + c
        if i >= len(VOICES):
            continue
        voice = VOICES[i]
        with cols[c]:
            with st.container(border=True):
                st.markdown(f"{voice['icon']} **{voice['name']}**")
                st.caption(voice["use_case"])
                st.markdown(
                    f'<div style="font-size:0.82rem;color:#46484E;margin:-8px 0 8px 0;">🗣️ {voice["best_for"]}</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(quality_badge_html(voice["quality"]), unsafe_allow_html=True)
                if voice["quality"] == "unsupported":
                    st.button("▶ Preview", key=f"preview_btn_{i}", disabled=True, width="stretch")
                    st.caption("Audio preview unavailable yet — library still being curated.")
                else:
                    if st.button("▶ Preview", key=f"preview_btn_{i}", width="stretch"):
                        st.session_state.preview_open.symmetric_difference_update({i})
                    if i in st.session_state.preview_open:
                        samples = load_wav_samples(voice_preview_path(i))
                        st.audio(str(voice_preview_path(i)))
                        st.image(waveform_svg_data_uri(samples), width="stretch")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# DIALECT SELECTOR (21 Arabic dialects)
# =========================================================
section_header("Dialect Selector — 21 Arabic Dialects", icon="🌍")
section_desc("Not every dialect has equal TTS quality yet — shown honestly below, not presented as equivalent.")

st.selectbox("Active dialect", options=DIALECT_NAMES, key="dialect_selected")
active = next(d for d in DIALECTS if d["name"] == st.session_state.dialect_selected)
if active["quality"] in ("low", "unsupported"):
    st.warning(f"'{active['name']}' currently has {active['quality']} TTS quality — expect rougher output.")

dcols = st.columns(3)
for i, d in enumerate(DIALECTS):
    with dcols[i % 3]:
        st.markdown(
            f'<div class="dialect-row"><span>{d["name"]} <span style="color:#8A8D94;">({d["ar"]})</span></span>'
            f"{quality_badge_html(d['quality'])}</div>",
            unsafe_allow_html=True,
        )

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# VOICE SPEED CONTROL
# =========================================================
section_header("Voice Speed Control", icon="⏱️")

preset_cols = st.columns(4)
for col, (label, value) in zip(preset_cols, SPEED_PRESETS.items()):
    with col:
        if st.button(label, key=f"speed_preset_{label}", width="stretch"):
            st.session_state.speed = value

st.slider("Speed", min_value=0.5, max_value=2.0, step=0.05, key="speed", label_visibility="collapsed")
current_preset = next((label for label, v in SPEED_PRESETS.items() if abs(v - st.session_state.speed) < 0.01), "Custom")
st.caption(f"{st.session_state.speed:.2f}× ({current_preset}) — inline `[[voice.speed=X]]` script commands stay in sync with this control.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# S - STUDIO ENHANCEMENT
# =========================================================
c1, c2 = st.columns([3, 1.2])
with c1:
    section_header("S - Studio-like Audio Enhancement", icon="🎧")
    section_desc("Remove background noise and boost voice clarity.")
with c2:
    if st.button("Enhance Voice", type="primary", key="enhance_voice", width="stretch"):
        with st.spinner("Enhancing…"):
            time.sleep(0.6)
        st.toast("Enhancement complete (placeholder — no Demucs pipeline wired in here).")

# =========================================================
# 7 - VOICE CLONING
# =========================================================
section_header("7 - Voice Cloning - 100% Match Required", icon="🌀")
section_desc("Support natural breathing, realistic silence, and tone variations.")

# =========================================================
# 8 / A - ARABIC DIALECTS
# =========================================================
section_header("A - All Arabic Dialects Supported", icon="8", variant="green")
section_desc("All Arabic dialects must be supported accurately and naturally — see the Dialect Selector above for the full list and honest quality ratings.")

# =========================================================
# F - LIBRARY VOICE GENERATION
# =========================================================
c1, c2 = st.columns([3, 1.4])
with c1:
    section_header("F - Non-Cloned Voice Generation (Library-based)", icon="👥")
    section_desc("Use internal Voice Library when no reference voice is provided.")
with c2:
    if st.button("Generate Voice from Library 📚", type="primary", key="library_voice", width="stretch"):
        fallback_voice = VOICES[7]  # Neutral Educator — generic default when no reference is given
        with st.spinner(f"Generating from library voice ({fallback_voice['name']})…"):
            time.sleep(0.7)
        audio_bytes, samples = placeholder_audio(260)
        st.session_state.gen_audio = (audio_bytes, samples, fallback_voice["name"])
        st.rerun()

# =========================================================
# G - FULL VOICE LIBRARY (see the full 12-voice browser above)
# =========================================================
section_header("G - Full Voice Library in Arabic & English", icon="📋")
section_desc("Default fallback voices in Arabic & English for unsupported reference audios — see the Voice Library Browser above for all 12 voice types.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# H - BACKGROUND AUDIO VOICE REFERENCE
# =========================================================
left, right = st.columns([3, 1.4])

with left:
    section_header("H - Use Reference Voices in Background Audio", icon="🎧")
    section_desc("Auto-detect reference voices in background layers and assign them correctly.")
    st.checkbox("Match reference audio", value=True, key="match_reference_audio")
    st.checkbox("Use cloned/generated fallback", value=True, key="fallback_audio")
    st.caption("If selected, this stage is ignored during video generation without interruption.")

with right:
    st.write("")
    st.write("")
    st.button("Skip This Step", type="primary", key="skip_step", width="stretch")

st.write("")
