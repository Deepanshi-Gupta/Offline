"""Standalone Streamlit page: Video / Motion Generation (WAN 2.2) & BIE
(§9 of the UI audit).

Built against Hasaballa_Plan.pdf §9 — explicitly scoped "Minimal UI (mostly
backend)". Era-appropriate motion and BIE are called out as running
"silently in backend" and must NOT be exposed as user controls, so they
only ever appear here as read-only status lines. The only real controls are
the camera-effect selector, body-motion toggle, and cinematic FX layer —
everything else (GPU queueing, quality-guard drift detection/auto-fix) is a
status indicator, per the UX note.

No real WAN 2.2 / BIE model is wired in — Generate simulates a GPU queue,
a generation delay, and a scripted quality-guard drift-and-autofix on one
demo scene, all synchronously (single button-click handler), unlike Smart
Director's chained state machine — there's no pause/resume requirement
here.

Run with:
    python -m streamlit run motion_generation_app.py
"""

import time

import streamlit as st

NUM_SCENES = 14
CAMERA_EFFECTS = ["Pan", "Zoom", "Dolly", "Rack Focus"]
FX_OPTIONS = ["Smoke", "Haze", "Explosions"]
QUALITY_GUARD_DEMO_SCENE = 6  # Scene 7 — always shows the drift/auto-fix state

STATUS_STYLE = {
    "not_animated": ("#F1F2F4", "#6B6E76", "Not Animated"),
    "queued": ("#EEF0F3", "#46484E", "Waiting for GPU"),
    "generating": ("#E8F0FE", "#1A56DB", "Generating…"),
    "quality_check": ("#FFF6E5", "#9A6B00", "Quality Guard Checking…"),
    "complete": ("#E3F7EA", "#187A43", "Complete"),
}

st.set_page_config(page_title="Motion Generation", layout="centered")

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { max-width: 800px; padding: 2rem 2.25rem; }

    .page-title { font-size: 1.8rem; font-weight: 800; color: #101114; margin-bottom: 0; }
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
    .silent-note {
        background: #F5F6F8; border: 1px dashed #DADCE0; border-radius: 10px;
        padding: 0.7rem 0.9rem; font-size: 0.85rem; color: #46484E; margin: 0.5rem 0;
    }
    .silent-note b { color: #26272B; }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    if "motion_scenes" not in st.session_state:
        st.session_state.motion_scenes = {
            i: {
                "status": "not_animated",
                "camera_effect": "Pan",
                "body_motion": True,
                "fx": set(),
                "quality_note": None,
            }
            for i in range(NUM_SCENES)
        }
    st.session_state.setdefault("motion_selected_scene", 0)


_init_state()


def status_badge_html(status: str) -> str:
    bg, fg, label = STATUS_STYLE[status]
    return f'<span class="status-badge" style="background:{bg};color:{fg};">{label}</span>'


def generate_motion(scene_idx: int):
    scene = st.session_state.motion_scenes[scene_idx]

    jobs_ahead = (scene_idx % 3) + 1
    q_ph = st.empty()
    scene["status"] = "queued"
    for jobs_left in range(jobs_ahead, 0, -1):
        q_ph.info(f"🖥️ Waiting for GPU — {jobs_left} job(s) ahead…")
        time.sleep(0.4)
    q_ph.empty()

    scene["status"] = "generating"
    progress = st.progress(0.0, text="Generating motion — era-appropriate style applied automatically…")
    for pct in (0.3, 0.6, 0.85, 1.0):
        time.sleep(0.35)
        progress.progress(pct, text="Generating motion — era-appropriate style applied automatically…")

    if scene_idx == QUALITY_GUARD_DEMO_SCENE:
        scene["status"] = "quality_check"
        st.warning("🛡️ Quality guard: drift detected on frames 42–58 — auto re-generating affected frames…")
        time.sleep(0.7)
        scene["quality_note"] = "Drift detected on frames 42–58 — auto re-generated, no action needed."
    else:
        scene["quality_note"] = "No drift detected."

    scene["status"] = "complete"


# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.4])
with h1:
    st.markdown('<div class="page-title">Motion Generation</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.3rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline</span></div>',
        unsafe_allow_html=True,
    )
st.caption("WAN 2.2 motion + BIE — scene properties panel. No real generation backend is wired in; this simulates timing and the quality-guard flow.")

# =========================================================
# SCENE SELECTOR + STATUS
# =========================================================
st.selectbox(
    "Scene",
    options=range(NUM_SCENES),
    format_func=lambda i: f"Scene {i + 1}",
    key="motion_selected_scene",
)
scene_idx = st.session_state.motion_selected_scene
scene = st.session_state.motion_scenes[scene_idx]

st.markdown(status_badge_html(scene["status"]), unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# USER-FACING CONTROLS
# =========================================================
st.markdown("**Camera Effect**")
ccols = st.columns(len(CAMERA_EFFECTS))
for i, effect in enumerate(CAMERA_EFFECTS):
    with ccols[i]:
        kind = "primary" if scene["camera_effect"] == effect else "secondary"
        if st.button(effect, key=f"cam_{scene_idx}_{effect}", type=kind, width="stretch"):
            scene["camera_effect"] = effect

st.write("")
t1, t2 = st.columns([1.3, 2])
with t1:
    scene["body_motion"] = st.toggle("Body Motion", value=scene["body_motion"], key=f"body_motion_{scene_idx}")
with t2:
    st.caption("Applies subject body movement on top of the camera effect (walking, gestures, etc.).")

st.write("")
st.markdown("**Cinematic FX Layer**")
fcols = st.columns(len(FX_OPTIONS))
for i, fx in enumerate(FX_OPTIONS):
    with fcols[i]:
        checked = st.checkbox(fx, value=fx in scene["fx"], key=f"fx_{scene_idx}_{fx}")
        if checked:
            scene["fx"].add(fx)
        else:
            scene["fx"].discard(fx)

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# SILENT / BACKEND-ONLY STATUS (never exposed as controls)
# =========================================================
st.markdown("**Automatic (no user control)**")
era_status = "Applied ✓" if scene["status"] == "complete" else ("Applying…" if scene["status"] == "generating" else "—")
bie_status = "Complete ✓" if scene["status"] == "complete" else ("Running…" if scene["status"] == "generating" else "—")
st.markdown(
    f'<div class="silent-note">🎞️ <b>Era-appropriate motion:</b> {era_status} — style is chosen automatically from '
    f'scene context, silently.<br>🧬 <b>BIE:</b> {bie_status} — runs in the background with no user-facing controls.</div>',
    unsafe_allow_html=True,
)

if scene["quality_note"]:
    icon = "🛡️" if "auto re-generated" in scene["quality_note"] else "✓"
    st.markdown(f'<div class="silent-note">{icon} <b>Quality Guard:</b> {scene["quality_note"]}</div>', unsafe_allow_html=True)

st.write("")
if st.button("▶ Generate Motion", type="primary", key=f"generate_{scene_idx}", width="stretch"):
    generate_motion(scene_idx)
    st.rerun()
