"""Standalone Streamlit page: Audio Layering, Sound Library & Compliance
(§7 of the UI audit).

Built against Hasaballa_Plan.pdf §7: a 16-category sound library browser
(era + region tags, search/filter, honest "not yet populated" empty states),
a religious-compliance toggle that is the client's flagship requirement —
given prominence, and legible ("N assets blocked") rather than silently
hiding anything — a layering/mixer panel (mute/solo/volume/fade, auto-duck,
LUFS meter), and a light Demucs standalone tool.

There is no real audio engine wired in: every "sample" is a short
synthesized placeholder tone (common/audio.py, cached per asset id) and
Demucs processing is a simulated multi-stage progress bar, not a real
model run.

Run with:
    python -m streamlit run audio_layering_app.py
"""

import time

import streamlit as st

from common.audio import samples_to_wav_bytes, synth_tone, waveform_svg_data_uri
from common.sound_library import (
    ASSETS,
    CATEGORIES,
    EMPTY_CATEGORIES,
    assets_in_category,
    flag_badge_html,
)

st.set_page_config(page_title="Audio Layering & Sound Library", layout="centered")

TRACK_NAMES = ["Dialogue", "Music", "SFX Layer 1", "SFX Layer 2", "Ambience"]
DEFAULT_TRACK_FOR_FLAG = {"music": "Music", "oud": "Music", "tarab": "Music", "neutral": "SFX Layer 1"}

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { max-width: 1050px; padding: 2rem 2.25rem; }

    .page-title { font-size: 2rem; font-weight: 800; color: #101114; margin-bottom: 0; }
    .offline-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: #E8F7EE; color: #187A43; border: 1px solid #BEE8CC;
        border-radius: 999px; padding: 3px 12px; font-size: 0.8rem; font-weight: 600;
    }
    .offline-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: #22B35E; }

    .section-label { font-weight: 700; font-size: 1.1rem; margin: 0.2rem 0 0.4rem 0; }
    .compliance-card {
        background: #FBF6EA; border: 1px solid #F0E2BC; border-radius: 14px;
        padding: 1.1rem 1.3rem; margin-bottom: 0.5rem;
    }
    .blocked-note {
        background: #FDECEC; color: #B42318; font-size: 0.8rem; font-weight: 600;
        border-radius: 8px; padding: 4px 10px; margin-top: 6px;
    }
    .lufs-track { background: #EEF0F3; border-radius: 6px; height: 14px; position: relative; overflow: hidden; }
    .lufs-fill { height: 100%; border-radius: 6px; }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("compliance_on", True)
    st.session_state.setdefault("sacred_context", False)
    st.session_state.setdefault("category_selected", CATEGORIES[0])
    st.session_state.setdefault("search_query", "")
    st.session_state.setdefault(
        "tracks",
        {name: {"volume": 70, "mute": False, "solo": False, "fade_in": 0.5, "fade_out": 0.5} for name in TRACK_NAMES},
    )
    st.session_state.setdefault("auto_duck", True)
    st.session_state.setdefault("mix_layers", [])
    st.session_state.setdefault("demucs_result", None)


_init_state()


@st.cache_data(show_spinner=False)
def asset_audio_bytes(asset_id: int):
    base = 180 + (asset_id * 17) % 260
    samples = synth_tone([base, base * 1.2, base * 0.9], duration_each=0.2)
    return samples_to_wav_bytes(samples), samples


def is_blocked(asset):
    if not st.session_state.compliance_on:
        return False, None
    if st.session_state.sacred_context and asset["flag"] in ("music", "oud", "tarab"):
        return True, "Sacred audio compliance — no music/oud/tarab during Adhan, Qur'an recitation, or Dua."
    return False, None


# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.2])
with h1:
    st.markdown('<div class="page-title">Audio Layering &amp; Sound Library</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.4rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline — no network used</span></div>',
        unsafe_allow_html=True,
    )
st.caption("Every sample below is a synthesized placeholder tone — no real sound library or audio engine is wired in.")

# =========================================================
# RELIGIOUS COMPLIANCE (flagship requirement — kept prominent)
# =========================================================
blocked_count = sum(1 for a in ASSETS if is_blocked(a)[0])
st.markdown('<div class="compliance-card">', unsafe_allow_html=True)
st.markdown("### 🛡️ Religious Compliance")
c1, c2 = st.columns(2)
with c1:
    st.toggle("Compliance filter enabled", key="compliance_on")
with c2:
    st.toggle("Scene contains Adhan / Qur'an recitation / Dua", key="sacred_context", disabled=not st.session_state.compliance_on)
if st.session_state.compliance_on and st.session_state.sacred_context:
    st.markdown(f'<div class="blocked-note">🚫 {blocked_count} of {len(ASSETS)} assets blocked for this scene — no music, oud, or tarab during sacred audio.</div>', unsafe_allow_html=True)
elif st.session_state.compliance_on:
    st.caption("No sacred audio in this scene right now — music/oud/tarab assets are allowed. Enabling the toggle above blocks them automatically.")
else:
    st.caption("Compliance filter is off — nothing is being blocked. Not recommended for scenes with sacred audio.")
st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# SOUND LIBRARY BROWSER
# =========================================================
st.markdown('<div class="section-label">📚 Sound Library — 16 Categories</div>', unsafe_allow_html=True)

fcol1, fcol2 = st.columns([2, 2])
with fcol1:
    st.selectbox("Category", options=CATEGORIES, key="category_selected")
with fcol2:
    st.text_input("Search", placeholder="Search this category…", key="search_query")

cat = st.session_state.category_selected
if cat in EMPTY_CATEGORIES:
    st.info(f"**{cat}** hasn't been populated yet — 0 of the target 50+ samples curated. This is the real state today, not a bug.")
else:
    items = assets_in_category(cat)
    q = st.session_state.search_query.strip().lower()
    if q:
        items = [a for a in items if q in a["name"].lower()]
    if not items:
        st.info("No samples match your search in this category.")
    for row_start in range(0, len(items), 3):
        cols = st.columns(3)
        for c in range(3):
            i = row_start + c
            if i >= len(items):
                continue
            asset = items[i]
            blocked, reason = is_blocked(asset)
            with cols[c]:
                with st.container(border=True):
                    st.markdown(f"**{asset['name']}**")
                    st.caption(f"{asset['era']} · {asset['region']}")
                    st.markdown(flag_badge_html(asset["flag"]), unsafe_allow_html=True)
                    if blocked:
                        st.markdown(f'<div class="blocked-note">🚫 Blocked — {reason}</div>', unsafe_allow_html=True)
                    pc1, pc2 = st.columns(2)
                    with pc1:
                        if st.button("▶ Preview", key=f"prev_{asset['id']}", width="stretch"):
                            st.session_state[f"show_prev_{asset['id']}"] = True
                    with pc2:
                        if st.button("+ Add to Mix", key=f"add_{asset['id']}", width="stretch", disabled=blocked):
                            st.session_state.mix_layers.append(
                                {"asset_id": asset["id"], "track": DEFAULT_TRACK_FOR_FLAG[asset["flag"]]}
                            )
                            st.toast(f"Added '{asset['name']}' to {DEFAULT_TRACK_FOR_FLAG[asset['flag']]}.")
                    if st.session_state.get(f"show_prev_{asset['id']}"):
                        audio_bytes, samples = asset_audio_bytes(asset["id"])
                        st.audio(audio_bytes, format="audio/wav")
                        st.image(waveform_svg_data_uri(samples, height=36), width="stretch")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# AUDIO LAYERING / MIXER PANEL
# =========================================================
st.markdown('<div class="section-label">🎚️ Audio Layering / Mixer</div>', unsafe_allow_html=True)

any_solo = any(t["solo"] for t in st.session_state.tracks.values())
mcols = st.columns(len(TRACK_NAMES))
for i, name in enumerate(TRACK_NAMES):
    track = st.session_state.tracks[name]
    with mcols[i]:
        with st.container(border=True):
            st.markdown(f"**{name}**")
            b1, b2 = st.columns(2)
            with b1:
                track["mute"] = st.checkbox("Mute", value=track["mute"], key=f"mute_{name}")
            with b2:
                track["solo"] = st.checkbox("Solo", value=track["solo"], key=f"solo_{name}")
            track["volume"] = st.slider("Volume", 0, 100, value=track["volume"], key=f"vol_{name}", label_visibility="collapsed")
            fc1, fc2 = st.columns(2)
            with fc1:
                track["fade_in"] = st.number_input("Fade in (s)", 0.0, 5.0, value=track["fade_in"], step=0.25, key=f"fi_{name}")
            with fc2:
                track["fade_out"] = st.number_input("Fade out (s)", 0.0, 5.0, value=track["fade_out"], step=0.25, key=f"fo_{name}")

# effective active volume per track (respecting solo/mute)
active_volumes = []
for name, t in st.session_state.tracks.items():
    if t["mute"]:
        continue
    if any_solo and not t["solo"]:
        continue
    active_volumes.append(t["volume"])

st.write("")
d1, d2 = st.columns([1.4, 2])
with d1:
    st.toggle("Auto-duck music under dialogue (−18 dB)", key="auto_duck")
with d2:
    music_track = st.session_state.tracks["Music"]
    if st.session_state.auto_duck and not music_track["mute"]:
        ducked = max(0, music_track["volume"] - 18)
        st.caption(f"Effective music level while dialogue plays: **{ducked}** (ducked from {music_track['volume']})")
    else:
        st.caption("Auto-duck is off — music stays at its set volume even under dialogue.")

avg_vol = (sum(active_volumes) / len(active_volumes)) if active_volumes else 0
lufs = -30 + (avg_vol / 100) * 16
target = -14.0
diff = abs(lufs - target)
lufs_color = "#22B35E" if diff <= 1 else ("#E3A008" if diff <= 4 else "#E2622A")
lufs_pct = max(0, min(100, (lufs + 40) / 30 * 100))
st.write("")
st.markdown(f"**LUFS Meter** — current: {lufs:.1f} LUFS · target: {target:.0f} LUFS")
st.markdown(
    f'<div class="lufs-track"><div class="lufs-fill" style="width:{lufs_pct:.0f}%;background:{lufs_color};"></div></div>',
    unsafe_allow_html=True,
)

if st.session_state.mix_layers:
    st.write("")
    st.markdown("**Assigned Clips**")
    for j, layer in enumerate(list(st.session_state.mix_layers)):
        asset = next(a for a in ASSETS if a["id"] == layer["asset_id"])
        lc1, lc2, lc3 = st.columns([2, 2, 1])
        with lc1:
            st.caption(f"{asset['name']} ({asset['category']})")
        with lc2:
            layer["track"] = st.selectbox(
                "Track", options=TRACK_NAMES, index=TRACK_NAMES.index(layer["track"]),
                key=f"layer_track_{j}", label_visibility="collapsed",
            )
        with lc3:
            if st.button("Remove", key=f"layer_remove_{j}", width="stretch"):
                st.session_state.mix_layers.pop(j)
                st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# DEMUCS STANDALONE AUDIO TOOL
# =========================================================
st.markdown('<div class="section-label">🎛️ Demucs — Standalone Audio Tool</div>', unsafe_allow_html=True)
st.caption("Raw audio in → noise removal → vocal separation → EQ → −14 LUFS out.")

raw_audio = st.file_uploader("Raw audio", type=["wav", "mp3"], label_visibility="collapsed", key="demucs_upload")
if st.button("Process", type="primary", key="demucs_process", disabled=raw_audio is None, width="stretch"):
    stages = ["Noise removal", "Vocal separation", "EQ", "Normalizing to −14 LUFS"]
    progress = st.progress(0.0, text="Starting…")
    for i, stage in enumerate(stages):
        time.sleep(0.4)
        progress.progress((i + 1) / len(stages), text=f"{stage}…")
    before_samples = synth_tone([140, 210, 175, 260], duration_each=0.15)
    after_samples = synth_tone([220, 330], duration_each=0.3)
    st.session_state.demucs_result = (
        samples_to_wav_bytes(before_samples), before_samples,
        samples_to_wav_bytes(after_samples), after_samples,
    )

if st.session_state.demucs_result:
    before_bytes, before_samples, after_bytes, after_samples = st.session_state.demucs_result
    bc1, bc2 = st.columns(2)
    with bc1:
        st.markdown("**Before**")
        st.audio(before_bytes, format="audio/wav")
        st.image(waveform_svg_data_uri(before_samples, color="#B42318"), width="stretch")
    with bc2:
        st.markdown("**After**")
        st.audio(after_bytes, format="audio/wav")
        st.image(waveform_svg_data_uri(after_samples, color="#187A43"), width="stretch")
    st.download_button("⬇ Download processed audio", data=after_bytes, file_name="demucs_output.wav", mime="audio/wav", width="stretch")
