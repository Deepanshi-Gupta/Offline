"""Standalone Streamlit page: Hasaballa GPT — Chat / Main Window (§1 of the
UI audit).

Rebuilt against the client-provided reference screenshot: an Arabic-first
script input box, mic (STT) button, reference image/audio attachments with
removable thumbnails, aspect-ratio selector, and Manual/Auto generate
buttons, plus a Saved Projects panel and a sidebar of shortcuts into the
rest of the platform's tools.

Approximate RTL, not a full logical mirror: Arabic text fields get
`direction: rtl` + right alignment, and elements are placed in the order
they read on screen — Streamlit's own layout primitives (columns/flex) are
authored LTR internally and don't auto-mirror from a CSS direction alone,
so a pixel-perfect logical-RTL swap isn't attempted here.

There is no real STT/microphone capture wired in (Streamlit can't access
the mic without a custom JS component) — recording is a UI-state
simulation, and "transcription" inserts placeholder text.

Run with:
    python -m streamlit run hasaballa_gpt_chat_app.py
"""

import time

import streamlit as st

from common.audio import waveform_svg_data_uri

st.set_page_config(page_title="Hasaballa GPT", layout="centered")

MAX_CHARS = 15000

SIDEBAR_LINKS = [
    ("Generate images", "🖼️", "image_generation_app.py"),
    ("Clone reference voices", "🎙️", "voice_cloning_app.py"),
    ("Enhance audio quality", "🎵", "audio_layering_app.py"),
    ("Generate audio", "🎵", "voice_cloning_app.py"),
    ("Image Animation & Lip sync", "🎬", "lip_sync_app.py"),
    ("Selective smart inpainting", "✨", None),
    ("Timeline", "🗂️", None),
]

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .stApp { background-color: #EEF0F2; }
    .block-container { max-width: 1000px; padding: 2rem 1.5rem; }

    .chat-card {
        background: #FFFFFF; border: 1px solid #E6E7EA; border-radius: 16px;
        padding: 1.25rem 1.5rem; box-shadow: 0 2px 10px rgba(20,20,30,0.04);
    }
    .chat-title { text-align: center; font-size: 1.3rem; font-weight: 800; color: #26314D; }
    .folder-btn button {
        background: #F5C453 !important; border: none !important; border-radius: 10px !important;
        font-size: 1.1rem !important; height: 2.4rem !important;
    }

    .rtl-text, .rtl-text textarea, .rtl-text input {
        direction: rtl; text-align: right;
    }

    .msg-area {
        background: #FBFBFC; border: 1px solid #ECEDF0; border-radius: 12px;
        min-height: 160px; padding: 1rem; margin-bottom: 0.6rem;
    }
    .msg-empty { color: #9AA0A6; text-align: center; padding: 2.2rem 0; direction: rtl; }
    .msg-bubble {
        background: #E8F0FE; border-radius: 10px; padding: 0.7rem 0.9rem;
        margin-bottom: 8px; direction: rtl; text-align: right; color: #1A3E9C; font-size: 0.92rem;
    }

    .char-counter { text-align: right; font-size: 0.78rem; color: #8A8D94; direction: ltr; unicode-bidi: isolate; }
    .char-counter.warn { color: #9A6B00; font-weight: 700; }
    .char-counter.danger { color: #B42318; font-weight: 700; }

    .recording-banner {
        background: #FDECEC; border: 1px solid #F5C2BE; color: #8C1D12; border-radius: 10px;
        padding: 6px 12px; font-size: 0.85rem; font-weight: 700; direction: rtl; text-align: right;
        display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
    }
    .rec-dot {
        width: 9px; height: 9px; border-radius: 50%; background: #E11D48; display: inline-block;
        animation: pulse 1s infinite;
    }
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.25; } 100% { opacity: 1; } }

    .attach-chip {
        display: inline-flex; align-items: center; gap: 6px; background: #F1F2F4;
        border-radius: 999px; padding: 3px 10px; font-size: 0.78rem; margin: 2px 4px 2px 0;
    }

    .sidebar-card {
        background: #FFFFFF; border: 1px solid #E6E7EA; border-radius: 16px;
        padding: 0.9rem; box-shadow: 0 2px 10px rgba(20,20,30,0.04);
    }
    div[data-testid="stButton"] button { border-radius: 10px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("script_text", "")
    st.session_state.setdefault("aspect_ratio", "16:9")
    st.session_state.setdefault("recording", False)
    st.session_state.setdefault("mic_unavailable_sim", False)
    st.session_state.setdefault("ref_image", None)
    st.session_state.setdefault("ref_audio", None)
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault(
        "saved_projects",
        [
            {"name": "مقهى الصباح (Morning Cafe)", "date": "2026-07-08", "ratio": "16:9"},
            {"name": "قصة الصياد (The Fisherman)", "date": "2026-07-05", "ratio": "9:16"},
        ],
    )


_init_state()


@st.dialog("📁 Saved Projects")
def saved_projects_dialog():
    if not st.session_state.saved_projects:
        st.info("No saved projects yet.")
    for i, proj in enumerate(list(st.session_state.saved_projects)):
        with st.container(border=True):
            c1, c2, c3 = st.columns([2.4, 1, 1])
            with c1:
                st.markdown(f"**{proj['name']}**")
                st.caption(f"{proj['date']} · {proj['ratio']}")
            with c2:
                if st.button("Open", key=f"open_proj_{i}", width="stretch"):
                    st.toast(f"Would open '{proj['name']}'.")
            with c3:
                if st.button("Delete", key=f"del_proj_{i}", width="stretch"):
                    st.session_state.saved_projects.pop(i)
                    st.rerun()


main_col, side_col = st.columns([3, 1.1])

with main_col:
    st.markdown('<div class="chat-card">', unsafe_allow_html=True)

    h1, h2, h3 = st.columns([1, 3, 1])
    with h1:
        st.markdown('<div class="folder-btn">', unsafe_allow_html=True)
        if st.button("📁", key="open_saved_projects", help="Saved Projects"):
            saved_projects_dialog()
        st.markdown("</div>", unsafe_allow_html=True)
    with h2:
        st.markdown('<div class="chat-title">Hasaballa GPT</div>', unsafe_allow_html=True)

    # message / response display
    if st.session_state.messages:
        bubbles = "".join(f'<div class="msg-bubble">{m}</div>' for m in st.session_state.messages)
        st.markdown(f'<div class="msg-area">{bubbles}</div>', unsafe_allow_html=True)
    else:
        st.markdown(
            '<div class="msg-area"><div class="msg-empty">لا توجد رسائل بعد — اكتب سيناريو أدناه للبدء.<br>'
            '<span style="font-size:0.8rem;">No messages yet — type a scenario below to begin.</span></div></div>',
            unsafe_allow_html=True,
        )

    # mic / recording state
    mc1, mc2 = st.columns([1, 6])
    with mc1:
        mic_label = "⏹" if st.session_state.recording else "🎙️"
        if st.button(mic_label, key="mic_btn", help="Voice input"):
            if st.session_state.recording:
                st.session_state.script_text = (
                    st.session_state.script_text + " [نص محوّل من الصوت — ميزة تحويل الصوت التجريبية]"
                )[:MAX_CHARS]
                st.session_state.recording = False
            elif st.session_state.mic_unavailable_sim:
                st.session_state.mic_error = True
            else:
                st.session_state.recording = True
                st.session_state.mic_error = False
            st.rerun()
    with mc2:
        if st.session_state.get("mic_error"):
            st.error("🎤 Microphone unavailable — check your input device in Settings.")
        elif st.session_state.recording:
            st.markdown('<div class="recording-banner"><span class="rec-dot"></span> جارٍ التسجيل... (Recording)</div>', unsafe_allow_html=True)
            st.image(waveform_svg_data_uri([0.2, 0.8, 0.4, 0.9, 0.3, 0.7, 0.5, 0.85, 0.35] * 6, color="#E11D48"), width="stretch")

    with st.container(key="script_input_rtl"):
        st.text_area(
            "Scenario",
            key="script_text",
            placeholder="اكتب هنا السيناريو...",
            height=110,
            max_chars=MAX_CHARS,
            label_visibility="collapsed",
        )

    n = len(st.session_state.script_text)
    counter_cls = "danger" if n > 14500 else ("warn" if n > 12000 else "")
    st.markdown(f'<div class="char-counter {counter_cls}">{n:,} / {MAX_CHARS:,}</div>', unsafe_allow_html=True)

    # attachments
    a1, a2 = st.columns(2)
    with a1:
        img_upl = st.file_uploader("🖼️ Reference image", type=["png", "jpg", "jpeg"], key="ref_image_upl", label_visibility="collapsed")
        if img_upl is not None:
            st.session_state.ref_image = img_upl.getvalue()
    with a2:
        audio_upl = st.file_uploader("🎵 Reference audio", type=["wav", "mp3"], key="ref_audio_upl", label_visibility="collapsed")
        if audio_upl is not None:
            st.session_state.ref_audio = audio_upl.getvalue()

    if st.session_state.ref_image:
        c1, c2 = st.columns([5, 1])
        with c1:
            st.image(st.session_state.ref_image, width=90)
        with c2:
            if st.button("✕", key="remove_ref_image", help="Remove reference image"):
                st.session_state.ref_image = None
                st.rerun()
    if st.session_state.ref_audio:
        c1, c2 = st.columns([5, 1])
        with c1:
            st.audio(st.session_state.ref_audio)
        with c2:
            if st.button("✕", key="remove_ref_audio", help="Remove reference audio"):
                st.session_state.ref_audio = None
                st.rerun()

    st.write("")
    r1, r2, r3, _ = st.columns([1, 1, 1, 3])
    for col, ratio in zip((r1, r2, r3), ("1:1", "9:16", "16:9")):
        with col:
            kind = "primary" if st.session_state.aspect_ratio == ratio else "secondary"
            if st.button(ratio, key=f"ar_{ratio}", type=kind, width="stretch"):
                st.session_state.aspect_ratio = ratio

    st.write("")
    g1, g2 = st.columns(2)
    with g1:
        manual_clicked = st.button("🎬 توليد يدوي", key="gen_manual", width="stretch")
    with g2:
        auto_clicked = st.button("✨ توليد تلقائي", key="gen_auto", type="primary", width="stretch")

    if manual_clicked or auto_clicked:
        mode = "Manual" if manual_clicked else "Auto"
        if not st.session_state.script_text.strip():
            st.warning("No scenario entered — nothing to generate.")
        else:
            with st.spinner(f"Processing ({mode} mode)…"):
                time.sleep(1.0)
            st.session_state.messages.append(
                f"✅ تم استلام السيناريو ({n:,} حرف) · {st.session_state.aspect_ratio} · وضع {mode} — بدأ التنفيذ. "
                f"راقب التقدم في Smart Director."
            )
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

with side_col:
    st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
    for label, icon, target in SIDEBAR_LINKS:
        if st.button(f"{icon}  {label}", key=f"nav_{label}", width="stretch"):
            if target:
                st.toast(f"Would open: {label} ({target})")
            else:
                st.toast(f"Would open: {label} (not built yet)")
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    '<style>.st-key-script_input_rtl textarea{direction:rtl;text-align:right;border-radius:10px;border:1px solid #DDDFE3;}</style>',
    unsafe_allow_html=True,
)

with st.expander("⚙️ Debug — simulate states"):
    st.checkbox("Simulate: microphone unavailable", key="mic_unavailable_sim")
