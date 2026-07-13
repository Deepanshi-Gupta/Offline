"""Standalone Streamlit page: Lip Sync (§6 of the UI audit).

Built against Hasaballa_Plan.pdf §6 "Lip Sync": a mode selector living inside
a timeline clip's properties (4 LatentSync presets: natural / radio / phone
/ megaphone), per-character isTalking indicators, and the full state model
(Not applied / Processing / Applied / Re-rendering / Failed-drift-detected).

Per the UX note, changing the mode never re-renders silently — it just marks
the change as pending until the user confirms in a dialog, because a
re-render is expensive. There is no real LatentSync model wired in: "sync
preview" plays a placeholder tone (common/audio.py) and status transitions
are simulated with a short delay.

Run with:
    python -m streamlit run lip_sync_app.py
"""

import time

import streamlit as st

from common.audio import samples_to_wav_bytes, synth_tone
from common.style import face_paths, image_to_data_uri

st.set_page_config(page_title="Lip Sync", layout="centered")

FACE_PATHS = face_paths()
CHARACTER_NAMES = ["Layla", "Omar"]

MODES = [
    {"key": "natural", "label": "Natural", "icon": "🗣️", "desc": "Default realistic lip movement matched to dialogue audio."},
    {"key": "radio", "label": "Radio", "icon": "📻", "desc": "Minimal mouth movement — voice-over / off-camera narration style."},
    {"key": "phone", "label": "Phone", "icon": "📱", "desc": "Constrained, phone-call framing — subtle motion for device close-ups."},
    {"key": "megaphone", "label": "Megaphone", "icon": "📢", "desc": "Exaggerated, amplified mouth motion for loud/shouting delivery."},
]
MODE_BY_KEY = {m["key"]: m for m in MODES}

CLIPS = [
    {"id": 0, "label": "Scene 3 · 00:12–00:18", "characters": ["Layla"]},
    {"id": 1, "label": "Scene 7 · 01:04–01:11", "characters": ["Omar"]},
    {"id": 2, "label": "Scene 12 · 02:30–02:36", "characters": ["Layla", "Omar"]},
]

STATUS_STYLE = {
    "not_applied": ("#F1F2F4", "#6B6E76", "Not Applied"),
    "processing": ("#E8F0FE", "#1A56DB", "Processing…"),
    "applied": ("#E3F7EA", "#187A43", "Applied ✓"),
    "failed": ("#FDECEC", "#B42318", "Failed — Drift Detected"),
}

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { max-width: 950px; padding: 2rem 2.25rem; }

    .page-title { font-size: 2rem; font-weight: 800; color: #101114; margin-bottom: 0; }
    .offline-pill {
        display: inline-flex; align-items: center; gap: 6px;
        background: #E8F7EE; color: #187A43; border: 1px solid #BEE8CC;
        border-radius: 999px; padding: 3px 12px; font-size: 0.8rem; font-weight: 600;
    }
    .offline-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: #22B35E; }

    .status-badge {
        display: inline-flex; align-items: center; gap: 6px; font-size: 0.85rem;
        font-weight: 700; padding: 3px 12px; border-radius: 999px;
    }
    .talk-badge {
        display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem;
        font-weight: 700; padding: 2px 10px; border-radius: 999px;
    }
    .avatar-sm img { border-radius: 10px; aspect-ratio: 1/1; object-fit: cover; }

    .mouth-bar { height: 10px; border-radius: 6px; margin-top: 10px; }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    if "clips" not in st.session_state:
        st.session_state.clips = {
            0: {"applied_mode": "natural", "pending_mode": None, "status": "applied",
                "talking": {"Layla": True}, "attempts": {}},
            1: {"applied_mode": None, "pending_mode": None, "status": "not_applied",
                "talking": {"Omar": False}, "attempts": {}},
            2: {"applied_mode": None, "pending_mode": None, "status": "not_applied",
                "talking": {"Layla": True, "Omar": False}, "attempts": {}},
        }
    st.session_state.setdefault("selected_clip", 0)
    st.session_state.setdefault("redetect_counter", 0)


_init_state()


def run_render(clip_id, mode):
    clip = st.session_state.clips[clip_id]
    with st.spinner(f"Re-rendering lip sync — {MODE_BY_KEY[mode]['label']} mode (simulated 45s+ job)…"):
        time.sleep(1.2)
    attempts = clip["attempts"].get(mode, 0)
    if mode == "megaphone" and attempts == 0:
        clip["status"] = "failed"
        clip["pending_mode"] = mode
        clip["attempts"][mode] = attempts + 1
    else:
        clip["applied_mode"] = mode
        clip["pending_mode"] = None
        clip["status"] = "applied"
        clip["attempts"][mode] = attempts + 1


@st.dialog("Confirm Re-render")
def confirm_rerender(clip_id, target_mode):
    clip = st.session_state.clips[clip_id]
    current_label = MODE_BY_KEY[clip["applied_mode"]]["label"] if clip["applied_mode"] else "no mode applied yet"
    st.warning(
        f"This clip currently has **{current_label}** lip sync. Switching to "
        f"**{MODE_BY_KEY[target_mode]['label']}** requires a full re-render — "
        f"this can take 45+ seconds on a full clip."
    )
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirm Re-render", type="primary", key=f"confirm_rr_{clip_id}", width="stretch"):
            run_render(clip_id, target_mode)
            st.rerun()
    with c2:
        if st.button("Cancel", key=f"cancel_rr_{clip_id}", width="stretch"):
            st.rerun()


def status_badge_html(status):
    bg, fg, label = STATUS_STYLE[status]
    return f'<span class="status-badge" style="background:{bg};color:{fg};">{label}</span>'


# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.2])
with h1:
    st.markdown('<div class="page-title">Lip Sync</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.4rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline — no network used</span></div>',
        unsafe_allow_html=True,
    )
st.caption("Lives inside a timeline clip's properties panel — shown here as its own screen. No LatentSync model is wired in; renders are simulated.")

# =========================================================
# CLIP SELECTOR
# =========================================================
clip_labels = [f"{c['label']} ({' + '.join(c['characters'])})" for c in CLIPS]
selected = st.selectbox("Clip", options=range(len(CLIPS)), format_func=lambda i: clip_labels[i], key="selected_clip")
clip_id = CLIPS[selected]["id"]
clip = st.session_state.clips[clip_id]
characters = CLIPS[selected]["characters"]

st.markdown(status_badge_html(clip["status"]), unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# isTalking INDICATORS
# =========================================================
st.markdown("**isTalking Detection**")
st.caption("Auto-detected from the dialogue track — lip sync only auto-activates for characters flagged as talking.")

tcols = st.columns(len(characters) + 1)
for i, name in enumerate(characters):
    char_idx = CHARACTER_NAMES.index(name)
    with tcols[i]:
        st.markdown('<div class="avatar-sm">', unsafe_allow_html=True)
        st.image(image_to_data_uri(FACE_PATHS[char_idx]), width="stretch")
        st.markdown("</div>", unsafe_allow_html=True)
        talking = clip["talking"].get(name, False)
        badge = (
            '<span class="talk-badge" style="background:#E3F7EA;color:#187A43;">🗣️ Talking</span>'
            if talking
            else '<span class="talk-badge" style="background:#F1F2F4;color:#6B6E76;">Silent</span>'
        )
        st.markdown(f"**{name}**<br>{badge}", unsafe_allow_html=True)
with tcols[-1]:
    st.write("")
    if st.button("🔄 Re-detect", key=f"redetect_{clip_id}", width="stretch"):
        st.session_state.redetect_counter += 1
        seed = st.session_state.redetect_counter + clip_id
        for i, name in enumerate(characters):
            clip["talking"][name] = bool((seed + i) % 2)
        st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# 4-MODE SELECTOR
# =========================================================
st.markdown("**Rendering Mode**")
mcols = st.columns(4)
for i, mode in enumerate(MODES):
    with mcols[i]:
        is_current = clip["pending_mode"] == mode["key"] or (
            clip["pending_mode"] is None and clip["applied_mode"] == mode["key"]
        )
        kind = "primary" if is_current else "secondary"
        if st.button(f"{mode['icon']} {mode['label']}", key=f"mode_{clip_id}_{mode['key']}", type=kind, width="stretch"):
            clip["pending_mode"] = mode["key"]
        st.caption(mode["desc"])

pending = clip["pending_mode"]
if pending and pending != clip["applied_mode"]:
    applied_label = MODE_BY_KEY[clip["applied_mode"]]["label"] if clip["applied_mode"] else "none"
    st.info(f"Pending change: **{MODE_BY_KEY[pending]['label']}** (currently applied: {applied_label}) — not re-rendered yet.")
    if st.button("▶ Apply / Re-render", type="primary", key=f"apply_{clip_id}", width="stretch"):
        confirm_rerender(clip_id, pending)

if clip["status"] == "failed":
    st.error(f"Drift detected while rendering **{MODE_BY_KEY[clip['pending_mode']]['label']}** mode — mouth sync fell out of alignment partway through.")
    if st.button("↻ Re-render again", type="primary", key=f"retry_{clip_id}", width="stretch"):
        run_render(clip_id, clip["pending_mode"])
        st.rerun()

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# SYNC PREVIEW
# =========================================================
st.markdown("**Sync Preview**")
prev_col, info_col = st.columns([1, 2])
with prev_col:
    main_char = characters[0]
    st.image(image_to_data_uri(FACE_PATHS[CHARACTER_NAMES.index(main_char)]), width="stretch")
    bar_color = "#22B35E" if clip["status"] == "applied" else "#D7D9DE"
    st.markdown(f'<div class="mouth-bar" style="background:{bar_color};"></div>', unsafe_allow_html=True)
with info_col:
    if clip["status"] == "applied":
        st.success(f"Synced with **{MODE_BY_KEY[clip['applied_mode']]['label']}** mode.")
        if st.button("▶ Play Preview", key=f"preview_{clip_id}", width="stretch"):
            samples = synth_tone([220, 246, 220, 196], duration_each=0.18)
            st.audio(samples_to_wav_bytes(samples), format="audio/wav")
    elif clip["status"] == "processing":
        st.info("Rendering in progress…")
    elif clip["status"] == "failed":
        st.warning("No usable preview — last render failed drift detection.")
    else:
        st.info("Not applied yet — pick a mode above and click Apply / Re-render.")
