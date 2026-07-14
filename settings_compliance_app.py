"""Standalone Streamlit page: Settings, Compliance & Offline Controls
(§14 of the UI audit).

Built against Hasaballa_Plan.pdf §14: the offline/online indicator is the
client's core trust question, so per the UX note it is rendered here as a
persistent, unmissable full-width banner — not a small corner pill like the
other screens use — and going online requires an explicit confirmation
dialog rather than a single click. Also covers religious compliance,
image-compliance sensitivity, model/path configuration (with a reachable
"model missing" state and re-check guidance), and a language/RTL setting.

No real network connection or model filesystem check is wired in —
"Connecting" is a timed simulation and "Re-check Path" simulates the user
having fixed the path externally.

Run with:
    python -m streamlit run settings_compliance_app.py
"""

import time

import streamlit as st

st.set_page_config(page_title="Settings & Compliance", layout="centered")

MODELS = [
    {"key": "sdxl", "name": "SDXL / FLUX (Image Generation)", "path": "D:/Models/sdxl-flux", "found": True},
    {"key": "wan", "name": "WAN 2.2 (Motion Generation)", "path": "D:/Models/wan2.2", "found": True},
    {"key": "latentsync", "name": "LatentSync (Lip Sync)", "path": "D:/Models/latentsync", "found": True},
    {"key": "tts", "name": "TTS Voice Library", "path": "D:/Models/tts-voices", "found": True},
    {"key": "whisper", "name": "Whisper (STT)", "path": "D:/Models/whisper-large-v3", "found": True},
    {"key": "nllb", "name": "NLLB-200 (Translation)", "path": "", "found": False},
]

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { max-width: 950px; padding: 1.5rem 2.25rem 2rem 2.25rem; }

    .page-title { font-size: 2rem; font-weight: 800; color: #101114; margin: 0.6rem 0 0 0; }
    .section-label { font-weight: 700; font-size: 1.05rem; margin: 1rem 0 0.5rem 0; }

    .conn-banner {
        display: flex; align-items: center; justify-content: space-between;
        border-radius: 14px; padding: 0.9rem 1.25rem; font-size: 1.02rem; font-weight: 700;
        margin-bottom: 0.5rem;
    }
    .conn-banner.offline { background: #E3F7EA; border: 1px solid #BEE8CC; color: #146134; }
    .conn-banner.connecting { background: #FBF6EA; border: 1px solid #F0E2BC; color: #7A4E00; }
    .conn-banner.online { background: #FDECEC; border: 2px solid #E2622A; color: #8C1D12; }

    .model-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; }
    .found-badge, .missing-badge {
        font-size: 0.78rem; font-weight: 700; padding: 2px 10px; border-radius: 999px;
    }
    .found-badge { background: #E3F7EA; color: #187A43; }
    .missing-badge { background: #FDECEC; color: #B42318; }

    .guidance-box {
        background: #F5F6F8; border: 1px dashed #DADCE0; border-radius: 10px;
        padding: 0.7rem 0.9rem; font-size: 0.85rem; color: #46484E; margin: 0.4rem 0 0.8rem 0;
    }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("conn_status", "offline")  # offline | connecting | online
    st.session_state.setdefault("religious_compliance", True)
    st.session_state.setdefault("image_compliance", True)
    st.session_state.setdefault("modesty_sensitivity", "Medium")
    st.session_state.setdefault("models", {m["key"]: dict(m) for m in MODELS})
    st.session_state.setdefault("ui_language", "Arabic")


_init_state()


@st.dialog("Go Online?")
def confirm_online():
    st.warning(
        "This will allow the app to connect to the internet. Nothing leaves this machine except through features "
        "you explicitly use while online (e.g. YouTube publishing). Generation, editing, and storage stay local "
        "either way."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Go Online", type="primary", key="confirm_online_btn", width="stretch"):
            st.session_state.conn_status = "connecting"
            st.rerun()
    with c2:
        if st.button("Cancel", key="cancel_online_btn", width="stretch"):
            st.rerun()


# =========================================================
# PERSISTENT CONNECTION BANNER — the client's core trust question
# =========================================================
status = st.session_state.conn_status
if status == "offline":
    st.markdown(
        '<div class="conn-banner offline">🔒 Offline — no data leaves this machine'
        '<span style="font-weight:400;font-size:0.85rem;">Default state</span></div>',
        unsafe_allow_html=True,
    )
elif status == "connecting":
    st.markdown('<div class="conn-banner connecting">🌐 Connecting…</div>', unsafe_allow_html=True)
    time.sleep(0.6)
    st.session_state.conn_status = "online"
    st.rerun()
else:
    st.markdown(
        '<div class="conn-banner online">🌐 Online — internet access is active'
        '<span style="font-weight:400;font-size:0.85rem;">Deliberately enabled</span></div>',
        unsafe_allow_html=True,
    )

st.markdown('<div class="page-title">Settings</div>', unsafe_allow_html=True)
st.caption("Compliance, offline controls, and model configuration for the Hasaballa AI Platform.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# SMART INTERNET ACCESS
# =========================================================
st.markdown('<div class="section-label">📡 Smart Internet Access</div>', unsafe_allow_html=True)
st.caption("Offline by default. The app never auto-connects — going online always requires this explicit action.")

if status == "offline":
    if st.button("🌐 Allow Internet Access", key="go_online_btn"):
        confirm_online()
elif status == "online":
    d1, d2 = st.columns(2)
    with d1:
        if st.button("🔌 Disconnect", key="disconnect_btn", width="stretch"):
            st.session_state.conn_status = "offline"
            st.rerun()
    with d2:
        if st.button("↩ Return to Offline", key="return_offline_btn", type="primary", width="stretch"):
            st.session_state.conn_status = "offline"
            st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# RELIGIOUS COMPLIANCE
# =========================================================
st.markdown('<div class="section-label">🛡️ Religious Compliance</div>', unsafe_allow_html=True)
st.toggle("Auto-block non-compliant audio (music/oud/tarab during Adhan, Qur'an recitation, or Dua)", key="religious_compliance")
st.caption("Enforced live in the Audio Layering screen (§7) whenever a scene is flagged as containing sacred audio.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# IMAGE COMPLIANCE / MODESTY FILTER
# =========================================================
st.markdown('<div class="section-label">🖼️ Image Compliance / Modesty Filter</div>', unsafe_allow_html=True)
st.toggle("Auto-reject and regenerate non-compliant imagery", key="image_compliance")
st.session_state.modesty_sensitivity = st.select_slider(
    "Sensitivity threshold", options=["Low", "Medium", "High"], value=st.session_state.modesty_sensitivity,
    key="modesty_slider", disabled=not st.session_state.image_compliance,
)
st.caption("Higher sensitivity rejects more borderline images automatically (§3). Enforced silently — flagged images are never shown to the user.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# MODEL / PATH CONFIGURATION
# =========================================================
st.markdown('<div class="section-label">📁 Model &amp; Path Configuration</div>', unsafe_allow_html=True)
for key, model in st.session_state.models.items():
    with st.container(border=True):
        mcol1, mcol2 = st.columns([2, 1])
        with mcol1:
            st.markdown(f"**{model['name']}**")
        with mcol2:
            if model["found"]:
                st.markdown('<div class="found-badge">✓ Found</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="missing-badge">✕ Missing</div>', unsafe_allow_html=True)
        model["path"] = st.text_input(
            "Path", value=model["path"], key=f"path_{key}", label_visibility="collapsed",
            placeholder="Model folder not set",
        )
        if not model["found"]:
            st.markdown(
                f'<div class="guidance-box">⚠ <b>{model["name"]}</b> was not found at this path. Download the '
                "model weights, place them in the folder above, then click Re-check.</div>",
                unsafe_allow_html=True,
            )
            if st.button(f"🔍 Re-check Path", key=f"recheck_{key}"):
                model["found"] = True
                st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# LANGUAGE / RTL SETTINGS
# =========================================================
st.markdown('<div class="section-label">🌐 Language / RTL</div>', unsafe_allow_html=True)
st.session_state.ui_language = st.selectbox("Interface language", options=["Arabic", "English"], index=["Arabic", "English"].index(st.session_state.ui_language), key="ui_language_select")
if st.session_state.ui_language == "Arabic":
    st.markdown(
        '<div style="direction:rtl;text-align:right;font-size:1.05rem;font-weight:600;">'
        "الواجهة تعرض من اليمين إلى اليسار تلقائيًا.</div>",
        unsafe_allow_html=True,
    )
    st.caption("RTL is applied automatically whenever Arabic is selected — navigation, icons, and timelines flow right-to-left.")
else:
    st.markdown('<div style="text-align:left;font-size:1.05rem;font-weight:600;">The interface renders left-to-right.</div>', unsafe_allow_html=True)
    st.caption("English is provided for developers/QA — Arabic remains the primary client-facing language.")
