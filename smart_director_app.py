"""Standalone Streamlit page: Smart Director / Pipeline Orchestrator (§8 of
the UI audit).

Built against Hasaballa_Plan.pdf §8: this is flagged as the screen users
will stare at for 45+ minutes, so it gets both an overall scene×stage
progress grid AND a prominent "what is happening right now" banner, per the
UX note. Auto vs Manual mode, per-stage skip controls (image / animation /
voice / compilation), a scripted failure at scene 12 of 14 (the doc's own
example) with retry/skip/abort, and Pause/Cancel that is genuinely
responsive — not just decorative.

Architecture note: instead of one blocking Python loop across all 56
scene×stage units (which could not be interrupted mid-run), each script
execution advances the pipeline by exactly one unit, then — if still
running — sleeps briefly and calls st.rerun() to chain to the next one.
Because every unit boundary is a fresh Streamlit script run, a Pause/Cancel
click is picked up before the next unit starts, giving real (not fake)
responsiveness within about one animation frame.

Run with:
    python -m streamlit run smart_director_app.py
"""

import time

import streamlit as st

STAGES = ["Image Generation", "Animation", "Voice", "Compilation"]
NUM_SCENES = 14
FAIL_SCENE_IDX = 11  # Scene 12 — the doc's own "failure at scene 12 of 14" example
FAIL_STAGE_IDX = 1  # Animation
SIM_MINUTES_PER_UNIT = 0.8  # cosmetic only — 14 scenes x 4 stages x 0.8 ≈ 45 min, matching the real spec

STATUS_ICON = {
    "pending": ("○", "#B7BAC1", "#F7F8FA"),
    "running": ("⏳", "#FFFFFF", "#2F6FEF"),
    "done": ("✓", "#FFFFFF", "#22B35E"),
    "skipped": ("–", "#8A8D94", "#E7E8EB"),
    "failed": ("✕", "#FFFFFF", "#B42318"),
}

st.set_page_config(page_title="Smart Director", layout="centered")

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { max-width: 980px; padding: 2rem 2.25rem; }

    .page-title { font-size: 2rem; font-weight: 800; color: #101114; margin-bottom: 0; }
    .offline-pill, .gpu-pill {
        display: inline-flex; align-items: center; gap: 6px;
        border-radius: 999px; padding: 3px 12px; font-size: 0.8rem; font-weight: 600;
    }
    .offline-pill { background: #E8F7EE; color: #187A43; border: 1px solid #BEE8CC; }
    .offline-pill .dot { width: 8px; height: 8px; border-radius: 50%; background: #22B35E; }
    .gpu-pill { background: #EEF0F3; color: #46484E; border: 1px solid #E2E4E8; margin-left: 8px; }

    .now-banner {
        background: #E8F0FE; border: 1px solid #C7DBFC; border-radius: 14px;
        padding: 1rem 1.25rem; margin: 0.8rem 0; font-size: 1.05rem; font-weight: 700;
        color: #1A3E9C;
    }
    .now-banner.paused { background: #FCEFD8; border-color: #F0DBA6; color: #7A4E00; }
    .now-banner.failed { background: #FDECEC; border-color: #F5C2BE; color: #8C1D12; }
    .now-banner.complete { background: #E3F7EA; border-color: #BEE8CC; color: #146134; }
    .now-banner.cancelled { background: #F1F2F4; border-color: #E2E4E8; color: #46484E; }

    .stepper { display: flex; gap: 10px; margin: 0.6rem 0 1rem 0; }
    .stepper .stage {
        flex: 1; text-align: center; padding: 8px 4px; border-radius: 10px;
        font-size: 0.82rem; font-weight: 700; border: 2px solid transparent;
    }

    .grid-wrap { overflow-x: auto; }
    table.grid { border-collapse: collapse; width: 100%; font-size: 0.82rem; }
    table.grid th { text-align: center; padding: 4px 6px; color: #46484E; font-weight: 700; }
    table.grid td { text-align: center; padding: 3px; }
    table.grid td.scene-label { text-align: left; color: #46484E; font-weight: 600; padding-right: 8px; white-space: nowrap; }
    .cell {
        display: inline-flex; align-items: center; justify-content: center;
        width: 26px; height: 26px; border-radius: 7px; font-size: 13px; font-weight: 700;
    }
    .cell.current { box-shadow: 0 0 0 2px #2F6FEF; }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("mode", "auto")
    st.session_state.setdefault("status", "idle")  # idle, running, paused, failed, cancelled, complete
    st.session_state.setdefault("cur_scene", 0)
    st.session_state.setdefault("cur_stage", 0)
    st.session_state.setdefault("grid", [["pending"] * len(STAGES) for _ in range(NUM_SCENES)])
    st.session_state.setdefault("stage_skip", {s: False for s in STAGES})
    st.session_state.setdefault("fail_triggered", False)
    st.session_state.setdefault("toasted_complete", False)


_init_state()


def _advance_to_next_stage():
    st.session_state.cur_scene = 0
    if st.session_state.cur_stage < len(STAGES) - 1:
        st.session_state.cur_stage += 1
        if st.session_state.mode == "manual":
            st.session_state.status = "paused"
    else:
        st.session_state.status = "complete"


def _advance_scene_or_stage():
    if st.session_state.cur_scene < NUM_SCENES - 1:
        st.session_state.cur_scene += 1
    else:
        _advance_to_next_stage()


def advance_one_step():
    stage_idx = st.session_state.cur_stage
    scene_idx = st.session_state.cur_scene
    stage_name = STAGES[stage_idx]

    if st.session_state.stage_skip[stage_name]:
        for s in range(NUM_SCENES):
            if st.session_state.grid[s][stage_idx] == "pending":
                st.session_state.grid[s][stage_idx] = "skipped"
        time.sleep(0.15)
        _advance_to_next_stage()
        return

    if scene_idx == FAIL_SCENE_IDX and stage_idx == FAIL_STAGE_IDX and not st.session_state.fail_triggered:
        st.session_state.grid[scene_idx][stage_idx] = "failed"
        st.session_state.fail_triggered = True
        st.session_state.status = "failed"
        return

    st.session_state.grid[scene_idx][stage_idx] = "done"
    _advance_scene_or_stage()


def reset_all():
    st.session_state.status = "idle"
    st.session_state.cur_scene = 0
    st.session_state.cur_stage = 0
    st.session_state.grid = [["pending"] * len(STAGES) for _ in range(NUM_SCENES)]
    st.session_state.fail_triggered = False
    st.session_state.toasted_complete = False


# =========================================================
# ADVANCE STATE (before any rendering, so the UI below reflects it)
# =========================================================
if st.session_state.status == "running":
    advance_one_step()

if st.session_state.status == "complete" and not st.session_state.toasted_complete:
    st.toast("✅ Pipeline complete — all scenes ready.")
    st.session_state.toasted_complete = True

# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.6])
with h1:
    st.markdown('<div class="page-title">Smart Director</div>', unsafe_allow_html=True)
with h2:
    gpu_state = "Active" if st.session_state.status == "running" else "Idle"
    st.markdown(
        '<div style="text-align:right;margin-top:0.4rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline</span>'
        f'<span class="gpu-pill">🖥️ GPU: {gpu_state}</span></div>',
        unsafe_allow_html=True,
    )
st.caption("Pipeline orchestrator — Auto or Manual mode across all 14 scenes. No real generation backend is wired in; this simulates timing and failure handling.")

# =========================================================
# NOW BANNER — "what is it doing right now" must be unmistakable
# =========================================================
status = st.session_state.status
cur_scene, cur_stage = st.session_state.cur_scene, st.session_state.cur_stage

if status == "idle":
    banner_cls, banner_text = "", "Idle — configure mode and skip controls, then start the pipeline."
elif status == "running":
    banner_cls, banner_text = "", f"⏳ Now processing: Scene {cur_scene + 1} of {NUM_SCENES} — {STAGES[cur_stage]}"
elif status == "paused":
    if cur_scene == 0 and cur_stage > 0:
        banner_cls, banner_text = "paused", f"⏸ Paused after {STAGES[cur_stage - 1]} — click Next Step to continue with {STAGES[cur_stage]}."
    else:
        banner_cls, banner_text = "paused", f"⏸ Paused at Scene {cur_scene + 1} — {STAGES[cur_stage]}. Click Next Step to continue."
elif status == "failed":
    banner_cls, banner_text = "failed", f"⚠ Failed: Scene {FAIL_SCENE_IDX + 1} of {NUM_SCENES} — {STAGES[FAIL_STAGE_IDX]}. The first {FAIL_SCENE_IDX} scenes are untouched and still complete."
elif status == "cancelled":
    done_units = sum(1 for row in st.session_state.grid for c in row if c in ("done", "skipped"))
    banner_cls, banner_text = "cancelled", f"⛔ Cancelled — {done_units}/{NUM_SCENES * len(STAGES)} steps completed so far are preserved. Resume anytime."
else:
    banner_cls, banner_text = "complete", "🎉 Pipeline complete — all 14 scenes are ready."

st.markdown(f'<div class="now-banner {banner_cls}">{banner_text}</div>', unsafe_allow_html=True)

# =========================================================
# OVERALL PROGRESS + ETA
# =========================================================
total_units = NUM_SCENES * len(STAGES)
completed_units = sum(1 for row in st.session_state.grid for c in row if c in ("done", "skipped"))
remaining_units = total_units - completed_units
eta_min = remaining_units * SIM_MINUTES_PER_UNIT
st.progress(completed_units / total_units, text=f"{completed_units}/{total_units} steps · ~{eta_min:.0f} min remaining")

# current-scene stepper (zoomed-in detail for the active scene)
st.markdown('<div class="stepper">', unsafe_allow_html=True)
stepper_html = ""
for i, stage_name in enumerate(STAGES):
    cell_status = st.session_state.grid[cur_scene][i]
    icon, fg, bg = STATUS_ICON[cell_status]
    border = "border:2px solid #2F6FEF;" if i == cur_stage and status in ("running", "failed") else ""
    stepper_html += f'<div class="stage" style="background:{bg};color:{fg};{border}">{icon} {stage_name}</div>'
st.markdown(stepper_html, unsafe_allow_html=True)
st.markdown("</div>", unsafe_allow_html=True)
st.caption(f"Detail for Scene {cur_scene + 1} (the scene currently in view)")

# =========================================================
# MODE + SKIP CONTROLS
# =========================================================
locked = status not in ("idle", "cancelled", "complete")
st.markdown("**Mode**")
m1, m2 = st.columns(2)
with m1:
    if st.button("🤖 Auto", key="mode_auto", type="primary" if st.session_state.mode == "auto" else "secondary", disabled=locked, width="stretch"):
        st.session_state.mode = "auto"
with m2:
    if st.button("🧑‍💻 Manual", key="mode_manual", type="primary" if st.session_state.mode == "manual" else "secondary", disabled=locked, width="stretch"):
        st.session_state.mode = "manual"
st.caption("Manual mode pauses after every stage so you can review before continuing. Auto runs straight through.")

st.markdown("**Per-Stage Skip**")
scols = st.columns(len(STAGES))
for i, stage_name in enumerate(STAGES):
    with scols[i]:
        st.session_state.stage_skip[stage_name] = st.checkbox(
            stage_name, value=st.session_state.stage_skip[stage_name], key=f"skip_{stage_name}", disabled=locked
        )

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# SCENE x STAGE GRID (overall progress, per-scene status)
# =========================================================
st.markdown("**Scene Queue — 14 Scenes**")
rows_html = ""
for s in range(NUM_SCENES):
    cells = ""
    for i in range(len(STAGES)):
        cell_status = st.session_state.grid[s][i]
        icon, fg, bg = STATUS_ICON[cell_status]
        is_current = (s == cur_scene and i == cur_stage and status in ("running", "failed"))
        cur_cls = "current" if is_current else ""
        cells += f'<td><span class="cell {cur_cls}" style="background:{bg};color:{fg};">{icon}</span></td>'
    rows_html += f'<tr><td class="scene-label">Scene {s + 1}</td>{cells}</tr>'

header_cells = "".join(f"<th>{s}</th>" for s in STAGES)
st.markdown(
    f'<div class="grid-wrap"><table class="grid"><thead><tr><th></th>{header_cells}</tr></thead>'
    f"<tbody>{rows_html}</tbody></table></div>",
    unsafe_allow_html=True,
)

st.write("")

# =========================================================
# ACTION BUTTONS PER STATE
# =========================================================
if status == "idle":
    if st.button("▶ Start Pipeline", type="primary", key="start_btn", width="stretch"):
        reset_all()
        st.session_state.status = "running"
        st.rerun()

elif status == "running":
    c1, c2 = st.columns(2)
    with c1:
        if st.button("⏸ Pause", key="pause_btn", width="stretch"):
            st.session_state.status = "paused"
            st.rerun()
    with c2:
        if st.button("⛔ Cancel", key="cancel_btn", width="stretch"):
            st.session_state.status = "cancelled"
            st.rerun()

elif status == "paused":
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Next Step", type="primary", key="next_step_btn", width="stretch"):
            st.session_state.status = "running"
            st.rerun()
    with c2:
        if st.button("⛔ Cancel", key="cancel_paused_btn", width="stretch"):
            st.session_state.status = "cancelled"
            st.rerun()

elif status == "failed":
    st.error(f"Stage failed at Scene {FAIL_SCENE_IDX + 1} — {STAGES[FAIL_STAGE_IDX]}. Choose how to proceed:")
    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("↻ Retry", type="primary", key="retry_btn", width="stretch"):
            st.session_state.grid[FAIL_SCENE_IDX][FAIL_STAGE_IDX] = "pending"
            st.session_state.status = "running"
            st.rerun()
    with c2:
        if st.button("⏭ Skip Scene", key="skip_scene_btn", width="stretch"):
            st.session_state.grid[FAIL_SCENE_IDX][FAIL_STAGE_IDX] = "skipped"
            _advance_scene_or_stage()
            st.session_state.status = "running"
            st.rerun()
    with c3:
        if st.button("⛔ Abort", key="abort_btn", width="stretch"):
            st.session_state.status = "cancelled"
            st.rerun()

elif status == "cancelled":
    c1, c2 = st.columns(2)
    with c1:
        if st.button("▶ Resume Pipeline", type="primary", key="resume_btn", width="stretch"):
            st.session_state.status = "running"
            st.rerun()
    with c2:
        if st.button("🔄 Start Fresh", key="restart_btn", width="stretch"):
            reset_all()
            st.rerun()

elif status == "complete":
    if st.button("🔄 Start New Batch", type="primary", key="new_batch_btn", width="stretch"):
        reset_all()
        st.rerun()

# =========================================================
# AUTO-CONTINUE
# =========================================================
if st.session_state.status == "running":
    time.sleep(0.12)
    st.rerun()
