"""Standalone Streamlit page: Subtitles, Captions & Translation (§10 of the
UI audit).

Built against Hasaballa_Plan.pdf §10 "Subtitles, Captions & Translation":
a manual subtitle block editor with real RTL Arabic alignment, a caption
styling panel whose preview renders actual reshaped-looking Arabic text
with diacritics (per the UX note — a Latin preview is useless here), a
timing-shift control with a live preview, real SRT import/export, a
burn-in toggle, a 5-language caption layer (Arabic + English + French +
Urdu + Malay) with a translating/failed state machine, and a per-scene
language override table.

No Whisper or NLLB model is wired in — "Auto-generate" seeds a fixed
5-block Arabic script and "Translate" fills in scripted placeholder text
after a simulated delay, with Urdu scripted to fail once so the
Translation-failed → Retry state is reachable every run. SRT export is
real text generation (no backend needed for that part); SRT import just
counts blocks in the uploaded file rather than fully re-parsing it.

Run with:
    python -m streamlit run subtitles_app.py
"""

import time

import streamlit as st

from common.scenes import scene_paths
from common.style import image_to_data_uri

st.set_page_config(page_title="Subtitles & Captions", layout="centered")

NUM_SCENES = 14
LANGUAGES = ["Arabic", "English", "French", "Urdu", "Malay"]
ALWAYS_ON = {"Arabic", "English"}  # the spec's "dual-language caption layer" pair
FONTS = ["Noto Naskh Arabic", "Tajawal", "Cairo", "Amiri"]
FAIL_LANG = "Urdu"  # scripted to fail once so Translating→Failed→Retry is reachable

SCENES = scene_paths()

DEFAULT_BLOCKS = [
    {"id": 0, "start_ms": 0, "end_ms": 2000, "ar": "مَرْحَبًا بِكُمْ فِي هَذِهِ الْقِصَّةِ."},
    {"id": 1, "start_ms": 2000, "end_ms": 4500, "ar": "كَانَ يَا مَا كَانَ، فِي قَدِيمِ الزَّمَانِ."},
    {"id": 2, "start_ms": 4500, "end_ms": 7000, "ar": "رَجُلٌ حَكِيمٌ يَعِيشُ فِي الصَّحْرَاءِ."},
    {"id": 3, "start_ms": 7000, "end_ms": 9500, "ar": "وَذَاتَ يَوْمٍ، سَمِعَ صَوْتًا غَرِيبًا."},
    {"id": 4, "start_ms": 9500, "end_ms": 12000, "ar": "فَقَرَّرَ أَنْ يَتْبَعَهُ."},
]
EN_TRANSLATION = {
    0: "Welcome to this story.",
    1: "Once upon a time, long ago.",
    2: "A wise man lived in the desert.",
    3: "One day, he heard a strange sound.",
    4: "So he decided to follow it.",
}

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { max-width: 1000px; padding: 2rem 2.25rem; }

    .page-title { font-size: 2rem; font-weight: 800; color: #101114; margin-bottom: 0; }
    .offline-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: #E8F7EE; color: #187A43; border: 1px solid #BEE8CC;
        border-radius: 999px; padding: 3px 12px; font-size: 0.8rem; font-weight: 600;
    }
    .offline-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: #22B35E; }
    .section-label { font-weight: 700; font-size: 1.05rem; margin: 1rem 0 0.5rem 0; }

    .rtl-textarea textarea {
        direction: rtl; text-align: right; border-radius: 10px;
        border: 1px solid #DDDFE3; font-size: 1rem;
    }

    .time-chip {
        display: inline-block; font-size: 0.78rem; font-weight: 700; color: #46484E;
        background: #F1F2F4; border-radius: 6px; padding: 2px 8px; margin-bottom: 4px;
    }
    .sync-warning {
        background: #FBF6EA; border: 1px solid #F0E2BC; color: #7A4E00;
        border-radius: 10px; padding: 0.7rem 0.9rem; font-size: 0.88rem; margin: 0.6rem 0;
    }
    .lang-badge {
        display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem;
        font-weight: 700; padding: 2px 10px; border-radius: 999px;
    }

    .caption-preview-frame {
        position: relative; border-radius: 12px; overflow: hidden; aspect-ratio: 16/9;
        background: #101114;
    }
    .caption-preview-frame img { width: 100%; height: 100%; object-fit: cover; opacity: 0.55; display: block; }
    .caption-preview-text {
        position: absolute; left: 5%; right: 5%; text-align: center; direction: rtl;
        padding: 6px 10px; border-radius: 8px; line-height: 1.5;
    }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("sub_status", "no_subtitles")  # no_subtitles | editing
    st.session_state.setdefault("blocks", [])
    st.session_state.setdefault("out_of_sync", False)
    st.session_state.setdefault("shift_ms", 0)
    st.session_state.setdefault("active_langs", {"Arabic", "English"})
    st.session_state.setdefault("translations", {"English": dict(EN_TRANSLATION)})
    st.session_state.setdefault("lang_status", {lang: "not_translated" for lang in LANGUAGES if lang not in ALWAYS_ON})
    st.session_state.setdefault("lang_attempts", {})
    st.session_state.setdefault(
        "style",
        {"font": FONTS[0], "size": 26, "color": "#FFFFFF", "bg_on": True, "bg_opacity": 60, "position": "Bottom"},
    )
    st.session_state.setdefault("scene_overrides", {i: "Use global track" for i in range(NUM_SCENES)})
    st.session_state.setdefault("burn_in", False)
    st.session_state.setdefault("preview_block", 0)
    st.session_state.setdefault("srt_import_note", None)


_init_state()


def ms_to_srt_ts(ms: int) -> str:
    ms = max(0, ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms_rest = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms_rest:03d}"


def blocks_to_srt(blocks) -> str:
    lines = []
    for i, b in enumerate(blocks, start=1):
        lines.append(str(i))
        lines.append(f"{ms_to_srt_ts(b['start_ms'])} --> {ms_to_srt_ts(b['end_ms'])}")
        lines.append(b["ar"])
        lines.append("")
    return "\n".join(lines)


def run_auto_generate():
    progress = st.progress(0.0, text="Transcribing audio (Whisper)…")
    for pct in (0.25, 0.55, 0.8, 1.0):
        time.sleep(0.3)
        progress.progress(pct, text="Transcribing audio (Whisper)…")
    st.session_state.blocks = [dict(b) for b in DEFAULT_BLOCKS]
    st.session_state.sub_status = "editing"


def run_translate(lang: str):
    attempts = st.session_state.lang_attempts.get(lang, 0)
    with st.spinner(f"Translating to {lang} (NLLB-200)…"):
        time.sleep(0.6)
    if lang == FAIL_LANG and attempts == 0:
        st.session_state.lang_status[lang] = "failed"
        st.session_state.lang_attempts[lang] = attempts + 1
        return
    st.session_state.translations[lang] = {
        b["id"]: f"[{lang}] {EN_TRANSLATION.get(b['id'], b['ar'])}" for b in st.session_state.blocks
    }
    st.session_state.lang_status[lang] = "translated"
    st.session_state.lang_attempts[lang] = attempts + 1


# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.2])
with h1:
    st.markdown('<div class="page-title">Subtitles &amp; Captions</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.4rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline — Whisper &amp; NLLB run locally</span></div>',
        unsafe_allow_html=True,
    )
st.caption("Independent subtitle layer. No Whisper/NLLB model is wired in here — transcription and translation are simulated.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# NO SUBTITLES / AUTO-GENERATE
# =========================================================
if st.session_state.sub_status == "no_subtitles":
    st.info("No subtitles yet for this project.")
    if st.button("🪄 Auto-generate from Audio (Whisper)", type="primary", key="auto_gen_btn", width="stretch"):
        run_auto_generate()
        st.rerun()
    st.stop()

blocks = st.session_state.blocks

# =========================================================
# OUT-OF-SYNC WARNING + AUTO-SYNC
# =========================================================
if st.session_state.out_of_sync:
    st.markdown(
        '<div class="sync-warning">⚠ Subtitles may be out of sync — the underlying audio track changed since these '
        "were generated.</div>",
        unsafe_allow_html=True,
    )
    if st.button("🔁 Auto-sync with Audio", type="primary", key="autosync_btn"):
        with st.spinner("Re-aligning subtitle timing to audio…"):
            time.sleep(0.5)
        st.session_state.out_of_sync = False
        st.rerun()
else:
    if st.button("🔧 Simulate: audio track changed", key="sim_desync_btn"):
        st.session_state.out_of_sync = True
        st.rerun()
    st.caption("Demo control — simulates the audio being re-edited so the out-of-sync warning above becomes reachable.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# MANUAL SUBTITLE BLOCK EDITOR
# =========================================================
st.markdown('<div class="section-label">✏️ Subtitle Blocks</div>', unsafe_allow_html=True)

for i, b in enumerate(blocks):
    with st.container(border=True):
        st.markdown(
            f'<span class="time-chip">{ms_to_srt_ts(b["start_ms"])[3:]} → {ms_to_srt_ts(b["end_ms"])[3:]}</span>',
            unsafe_allow_html=True,
        )
        tcol1, tcol2, tcol3 = st.columns([1, 1, 1])
        with tcol1:
            b["start_ms"] = st.number_input("Start (ms)", min_value=0, value=b["start_ms"], step=100, key=f"start_{b['id']}")
        with tcol2:
            b["end_ms"] = st.number_input("End (ms)", min_value=0, value=b["end_ms"], step=100, key=f"end_{b['id']}")
        with tcol3:
            st.write("")
            if st.button("🗑 Delete", key=f"del_{b['id']}", width="stretch"):
                st.session_state.blocks = [x for x in blocks if x["id"] != b["id"]]
                st.rerun()
        with st.container(key=f"rtl_wrap_{b['id']}"):
            st.markdown('<div class="rtl-textarea">', unsafe_allow_html=True)
            b["ar"] = st.text_area("Arabic", value=b["ar"], key=f"ar_{b['id']}", label_visibility="collapsed", height=68)
            st.markdown("</div>", unsafe_allow_html=True)
        if "English" in st.session_state.active_langs:
            st.caption(f"EN: {st.session_state.translations.get('English', {}).get(b['id'], '—')}")

if st.button("+ Add Block", key="add_block_btn"):
    new_id = (max((b["id"] for b in blocks), default=-1)) + 1
    last_end = blocks[-1]["end_ms"] if blocks else 0
    st.session_state.blocks.append({"id": new_id, "start_ms": last_end, "end_ms": last_end + 2000, "ar": ""})
    st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# TIMING SHIFT — live preview
# =========================================================
st.markdown('<div class="section-label">⏱ Timing Shift</div>', unsafe_allow_html=True)
shift_col1, shift_col2 = st.columns([2, 3])
with shift_col1:
    st.session_state.shift_ms = st.number_input(
        "Shift all blocks by (ms, ± allowed)", value=st.session_state.shift_ms, step=50, key="shift_input"
    )
with shift_col2:
    if blocks:
        b0 = blocks[0]
        preview_start = ms_to_srt_ts(b0["start_ms"] + st.session_state.shift_ms)[3:]
        preview_end = ms_to_srt_ts(b0["end_ms"] + st.session_state.shift_ms)[3:]
        st.caption(f"Live preview — Block 1 would move to **{preview_start} → {preview_end}**")
if st.button("Apply Shift to All Blocks", key="apply_shift_btn", disabled=st.session_state.shift_ms == 0):
    for b in st.session_state.blocks:
        b["start_ms"] = max(0, b["start_ms"] + st.session_state.shift_ms)
        b["end_ms"] = max(0, b["end_ms"] + st.session_state.shift_ms)
    st.session_state.shift_ms = 0
    st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# CAPTION STYLING PANEL — must render real Arabic w/ diacritics
# =========================================================
st.markdown('<div class="section-label">🎨 Caption Styling</div>', unsafe_allow_html=True)
style = st.session_state.style
scol1, scol2, scol3 = st.columns(3)
with scol1:
    style["font"] = st.selectbox("Font", options=FONTS, index=FONTS.index(style["font"]), key="style_font")
    style["size"] = st.slider("Size (px)", 16, 48, value=style["size"], key="style_size")
with scol2:
    style["color"] = st.color_picker("Text color", value=style["color"], key="style_color")
    style["position"] = st.radio("Position", ["Top", "Bottom"], index=["Top", "Bottom"].index(style["position"]), key="style_position", horizontal=True)
with scol3:
    style["bg_on"] = st.toggle("Background box", value=style["bg_on"], key="style_bg_on")
    style["bg_opacity"] = st.slider("Background opacity (%)", 0, 100, value=style["bg_opacity"], key="style_bg_opacity", disabled=not style["bg_on"])

if blocks:
    st.session_state.preview_block = st.selectbox(
        "Preview block", options=range(len(blocks)), format_func=lambda i: f"Block {i + 1}", key="preview_block_select"
    )
    pb = blocks[st.session_state.preview_block]
    bg_style = f"background: rgba(0,0,0,{style['bg_opacity'] / 100:.2f});" if style["bg_on"] else ""
    pos_style = "top: 6%;" if style["position"] == "Top" else "bottom: 6%;"
    scene_uri = image_to_data_uri(SCENES[st.session_state.preview_block % len(SCENES)])
    st.markdown(
        f'<div class="caption-preview-frame"><img src="{scene_uri}" />'
        f'<div class="caption-preview-text" style="{pos_style}{bg_style}font-family:\'{style["font"]}\',sans-serif;'
        f'font-size:{style["size"]}px;color:{style["color"]};">{pb["ar"] or "(empty block)"}</div></div>',
        unsafe_allow_html=True,
    )
    st.caption("Preview renders real reshaped Arabic with diacritics — never a Latin placeholder.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# LANGUAGE / DUBBING SELECTOR
# =========================================================
st.markdown('<div class="section-label">🌐 Caption Languages</div>', unsafe_allow_html=True)
st.caption("Arabic + English form the required dual-language layer and stay on. Add up to 3 more via NLLB-200 translation.")

lcols = st.columns(len(LANGUAGES))
for i, lang in enumerate(LANGUAGES):
    with lcols[i]:
        if lang in ALWAYS_ON:
            st.markdown(f'<span class="lang-badge" style="background:#E3F7EA;color:#187A43;">✓ {lang}</span>', unsafe_allow_html=True)
            continue
        status = st.session_state.lang_status[lang]
        checked = st.checkbox(lang, value=lang in st.session_state.active_langs, key=f"lang_on_{lang}")
        if checked:
            st.session_state.active_langs.add(lang)
        else:
            st.session_state.active_langs.discard(lang)
            continue
        if status == "not_translated":
            if st.button("Translate", key=f"translate_{lang}", width="stretch"):
                run_translate(lang)
                st.rerun()
        elif status == "translated":
            st.markdown('<span class="lang-badge" style="background:#E3F7EA;color:#187A43;">✓ Translated</span>', unsafe_allow_html=True)
        elif status == "failed":
            st.markdown('<span class="lang-badge" style="background:#FDECEC;color:#B42318;">✕ Failed</span>', unsafe_allow_html=True)
            if st.button("↻ Retry", key=f"retry_{lang}", type="primary", width="stretch"):
                run_translate(lang)
                st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# PER-SCENE LANGUAGE OVERRIDE
# =========================================================
with st.expander("🎬 Per-Scene Language Override (14 scenes)"):
    override_options = ["Use global track"] + LANGUAGES
    for s in range(NUM_SCENES):
        ocol1, ocol2 = st.columns([1, 2])
        with ocol1:
            st.caption(f"Scene {s + 1}")
        with ocol2:
            st.session_state.scene_overrides[s] = st.selectbox(
                f"Override scene {s + 1}", options=override_options,
                index=override_options.index(st.session_state.scene_overrides[s]),
                key=f"override_{s}", label_visibility="collapsed",
            )

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# SRT IMPORT / EXPORT + BURN-IN
# =========================================================
st.markdown('<div class="section-label">📄 SRT Import / Export</div>', unsafe_allow_html=True)
icol1, icol2 = st.columns(2)
with icol1:
    uploaded = st.file_uploader("Import .srt", type=["srt"], key="srt_upload")
    if uploaded is not None:
        text = uploaded.getvalue().decode("utf-8", errors="ignore")
        count = sum(1 for line in text.splitlines() if "-->" in line)
        st.session_state.srt_import_note = f"Imported file contains {count} timed block(s) — review before replacing your current blocks."
    if st.session_state.srt_import_note:
        st.info(st.session_state.srt_import_note)
with icol2:
    st.download_button(
        "⬇ Export current blocks as .srt",
        data=blocks_to_srt(blocks).encode("utf-8"),
        file_name="subtitles.srt",
        mime="text/plain",
        width="stretch",
        disabled=not blocks,
    )

st.write("")
b1, b2 = st.columns([1.4, 2])
with b1:
    st.session_state.burn_in = st.toggle("Burn subtitles into video at export", value=st.session_state.burn_in, key="burn_in_toggle")
with b2:
    st.caption(
        "When on, captions are permanently rendered into the video during Export (§11). When off, subtitles stay a "
        "separate, removable track."
    )
