"""Standalone Streamlit page: Image Generation (§3 of the UI audit).

Rebuilt against Hasaballa_Plan.pdf §3 "Image Generation": a 14-scene batch
generator with seed-based reproducibility, a per-scene review grid carrying
its own state (queued / generating / success / failed / compliance-rejected
/ manual review), per-image regenerate + approve/reject, and a manual-review
queue for repeated compliance failures (Addendum A4).

There is no local SDXL/FLUX model wired in — thumbnails are offline
procedural placeholders (assets/scenes) and the "compliance filter" /
"failures" are scripted for three fixed demo scenes so every run reliably
shows every required state. Real generation would replace `run_batch()`.

Run with:
    python -m streamlit run image_generation_app.py
"""

import time

import streamlit as st

from common.style import face_paths, image_to_data_uri, inject_base_css, reference_paths
from common.scenes import scene_paths

st.set_page_config(page_title="Image Generation", layout="centered")
inject_base_css(card=False)

TOTAL_SCENES = 14
# fixed demo scenes (0-indexed) so every batch run reliably exercises every
# state the spec calls for, regardless of seed
COMPLIANCE_DEMO_IDX = 4       # rejected by compliance filter, then auto-regenerated
RETRY_DEMO_IDX = 8            # fails once, needs a manual Retry click
MANUAL_REVIEW_DEMO_IDX = 11   # fails repeatedly -> manual review (spec's own "scene 12 of 14" example)

scenes_imgs = scene_paths()
faces = face_paths()
refs = reference_paths()

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
    .section-label { font-weight: 700; font-size: 1rem; margin: 1.1rem 0 0.5rem 0; }

    .st-key-prompt_rtl textarea {
        direction: rtl; text-align: right; border-radius: 12px;
        border: 1px solid #DDDFE3; font-size: 1rem;
    }

    .scene-tile {
        border-radius: 10px; overflow: hidden; aspect-ratio: 3/2;
        display: flex; align-items: center; justify-content: center;
        background: #EEF0F3; border: 1px solid #E2E4E8; position: relative;
    }
    .scene-tile img { width: 100%; height: 100%; object-fit: cover; display: block; }
    .scene-tile.queued { color: #8A8D94; font-size: 0.85rem; }
    .scene-tile.generating { color: #2F6FEF; font-size: 0.85rem; font-weight: 600; }
    .scene-tile.compliance { background: #FFF6E5; color: #9A6B00; font-size: 0.78rem; font-weight: 600; text-align:center; padding: 4px; }
    .scene-tile.failed { background: #FDECEC; color: #B42318; font-size: 0.85rem; font-weight: 600; }
    .scene-tile.manual_review { background: #FDECEC; color: #B42318; font-size: 0.78rem; font-weight: 600; text-align:center; padding:4px; }
    .scene-tile.skipped { background: #F1F2F4; color: #8A8D94; font-size: 0.85rem; }

    .scene-caption { font-size: 0.78rem; color: #46484E; margin: 4px 0 2px 0; text-align: center; }
    .badge-approved { color: #187A43; font-weight: 700; font-size: 0.78rem; text-align:center; }
    .badge-rejected { color: #B42318; font-weight: 700; font-size: 0.78rem; text-align:center; }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("gen_seed", 42)
    st.session_state.setdefault("seed_locked", True)
    st.session_state.setdefault("batch", None)  # None = empty state, never generated
    st.session_state.setdefault("batch_running", False)


_init_state()


def hue_for_seed(seed: int) -> int:
    return (int(seed) * 37) % 360


def scene_thumb_html(idx: int) -> str:
    hue = hue_for_seed(st.session_state.gen_seed)
    uri = image_to_data_uri(scenes_imgs[idx % len(scenes_imgs)])
    return f'<div class="scene-tile"><img style="filter: hue-rotate({hue}deg)" src="{uri}" /></div>'


def render_grid_html(placeholder):
    """Pure-HTML grid used only while the batch simulation is animating —
    no interactive widgets here, they take over once the run settles."""
    batch = st.session_state.batch
    cells = []
    for i in range(TOTAL_SCENES):
        status = batch[i]["status"]
        if status == "success":
            inner = scene_thumb_html(i)
        elif status == "generating":
            inner = '<div class="scene-tile generating">Generating…</div>'
        elif status == "compliance":
            inner = '<div class="scene-tile compliance">🛡️ Compliance check<br/>adjusting image…</div>'
        elif status == "failed":
            inner = '<div class="scene-tile failed">⚠ Failed</div>'
        else:
            inner = '<div class="scene-tile queued">Queued</div>'
        cells.append(
            f'<div style="flex:1 1 0;min-width:0;">{inner}'
            f'<div class="scene-caption">Scene {i + 1}</div></div>'
        )
    rows = [cells[0:7], cells[7:14]]
    html = "".join(
        f'<div style="display:flex;gap:10px;margin-bottom:10px;">{"".join(row)}</div>' for row in rows
    )
    placeholder.markdown(html, unsafe_allow_html=True)


def run_batch():
    st.session_state.batch = [{"status": "queued", "approved": None} for _ in range(TOTAL_SCENES)]
    st.session_state.batch_running = True

    progress = st.progress(0.0, text="Starting batch…")
    grid_ph = st.empty()
    render_grid_html(grid_ph)

    for i in range(TOTAL_SCENES):
        st.session_state.batch[i]["status"] = "generating"
        render_grid_html(grid_ph)
        time.sleep(0.12)

        if i == COMPLIANCE_DEMO_IDX:
            st.session_state.batch[i]["status"] = "compliance"
            render_grid_html(grid_ph)
            time.sleep(0.35)
            st.session_state.batch[i]["status"] = "success"
        elif i == RETRY_DEMO_IDX:
            st.session_state.batch[i]["status"] = "failed"
        elif i == MANUAL_REVIEW_DEMO_IDX:
            st.session_state.batch[i]["status"] = "manual_review"
        else:
            st.session_state.batch[i]["status"] = "success"

        progress.progress((i + 1) / TOTAL_SCENES, text=f"Generating scene {i + 1} of {TOTAL_SCENES}")
        render_grid_html(grid_ph)

    st.session_state.batch_running = False
    st.rerun()


@st.dialog("Regenerate Scene")
def regen_dialog(idx: int):
    status = st.session_state.batch[idx]["status"]
    if status not in ("manual_review",):
        st.markdown(scene_thumb_html(idx), unsafe_allow_html=True)
    else:
        st.info("This scene was withheld for manual review — no preview is shown for a flagged image.")

    st.text_input("Prompt override (optional)", key=f"regen_prompt_{idx}", placeholder="اتركه فارغًا لاستخدام نفس الوصف")
    st.number_input("Seed override", value=st.session_state.gen_seed, key=f"regen_seed_{idx}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Confirm Regenerate", type="primary", key=f"confirm_regen_{idx}", width="stretch"):
            with st.spinner("Regenerating…"):
                time.sleep(0.6)
            st.session_state.batch[idx] = {"status": "success", "approved": None}
            st.rerun()
    with c2:
        if st.button("Cancel", key=f"cancel_regen_{idx}", width="stretch"):
            st.rerun()


def render_settled_grid():
    batch = st.session_state.batch
    counts = {"success": 0, "failed": 0, "manual_review": 0, "skipped": 0}
    for s in batch:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    approved = sum(1 for s in batch if s.get("approved") is True)
    st.caption(
        f"{counts.get('success', 0)} succeeded · {approved} approved · "
        f"{counts.get('failed', 0)} need retry · {counts.get('manual_review', 0)} need manual review · "
        f"{counts.get('skipped', 0)} skipped"
    )

    for row_start in (0, 7):
        cols = st.columns(7)
        for c in range(7):
            i = row_start + c
            scene = batch[i]
            with cols[c]:
                status = scene["status"]
                if status == "success":
                    st.markdown(scene_thumb_html(i), unsafe_allow_html=True)
                elif status == "failed":
                    st.markdown('<div class="scene-tile failed">⚠ Failed</div>', unsafe_allow_html=True)
                elif status == "manual_review":
                    st.markdown(
                        '<div class="scene-tile manual_review">🚩 Needs<br/>manual review</div>',
                        unsafe_allow_html=True,
                    )
                elif status == "skipped":
                    st.markdown('<div class="scene-tile skipped">Skipped</div>', unsafe_allow_html=True)
                st.markdown(f'<div class="scene-caption">Scene {i + 1}</div>', unsafe_allow_html=True)

                if status == "success":
                    if scene.get("approved") is True:
                        st.markdown('<div class="badge-approved">✓ Approved</div>', unsafe_allow_html=True)
                    elif scene.get("approved") is False:
                        st.markdown('<div class="badge-rejected">✕ Rejected</div>', unsafe_allow_html=True)
                    ac1, ac2 = st.columns(2)
                    with ac1:
                        if st.button("✓", key=f"approve_{i}", width="stretch", help="Approve"):
                            scene["approved"] = True
                            st.rerun()
                    with ac2:
                        if st.button("✕", key=f"reject_{i}", width="stretch", help="Reject"):
                            scene["approved"] = False
                            st.rerun()
                    if st.button("↻ Regenerate", key=f"regen_{i}", width="stretch"):
                        regen_dialog(i)
                elif status == "failed":
                    if st.button("Retry", key=f"retry_{i}", type="primary", width="stretch"):
                        with st.spinner("Retrying…"):
                            time.sleep(0.5)
                        scene["status"] = "success"
                        st.rerun()


def render_manual_review_queue():
    flagged = [i for i, s in enumerate(st.session_state.batch) if s["status"] == "manual_review"]
    if not flagged:
        return
    st.markdown('<div class="section-label">🚩 Manual Review Needed</div>', unsafe_allow_html=True)
    for i in flagged:
        with st.container(border=True):
            st.markdown(
                f"**Scene {i + 1}** — repeated compliance rejection, no image is shown for a flagged scene."
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("↻ Regenerate", key=f"mr_regen_{i}", width="stretch"):
                    regen_dialog(i)
            with c2:
                if st.button("✏️ Edit Prompt", key=f"mr_edit_{i}", width="stretch"):
                    regen_dialog(i)
            with c3:
                if st.button("⏭️ Skip", key=f"mr_skip_{i}", width="stretch"):
                    st.session_state.batch[i]["status"] = "skipped"
                    st.rerun()


# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.2])
with h1:
    st.markdown('<div class="page-title">Image Generation</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.4rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline — no network used</span></div>',
        unsafe_allow_html=True,
    )

# =========================================================
# GENERATION PANEL
# =========================================================
with st.container(key="prompt_rtl"):
    st.text_area(
        "Prompt (Arabic)",
        value="رجل وامرأة يتحدثان في مقهى",
        label_visibility="collapsed",
        height=100,
    )

s1, s2, s3 = st.columns([1.3, 1.3, 2])
with s1:
    st.number_input("Seed", value=st.session_state.gen_seed, key="gen_seed", step=1)
with s2:
    st.toggle("Lock seed", key="seed_locked")
with s3:
    st.file_uploader(
        "Character reference-image slot",
        type=["png", "jpg", "jpeg"],
        label_visibility="collapsed",
        key="char_ref_upload",
    )
st.caption("Reference-image slot — used to keep the same character identity across the batch.")

st.markdown("<hr/>", unsafe_allow_html=True)

# style reference row kept from the original mockup (not a §3 spec item, but harmless additive)
r1, r2 = st.columns([3, 1.2])
with r1:
    st.markdown(f'<div class="section-label">Style Reference Images ({len(refs)})</div>', unsafe_allow_html=True)
with r2:
    st.checkbox("Arabic Text", value=True, key="arabic_text")
ref_cols = st.columns(5)
for i, path in enumerate(refs):
    with ref_cols[i]:
        st.image(image_to_data_uri(path), width="stretch")

st.write("")
gen_col, cancel_col = st.columns([3, 1])
with gen_col:
    if st.button(f"Generate {TOTAL_SCENES}-Scene Batch", type="primary", key="generate_batch_btn", width="stretch"):
        run_batch()
with cancel_col:
    st.button("Cancel", key="cancel_batch_btn", width="stretch", disabled=not st.session_state.batch_running)

# =========================================================
# BATCH GRID
# =========================================================
st.markdown('<div class="section-label">Batch — 14 Scenes</div>', unsafe_allow_html=True)

if st.session_state.batch is None:
    st.info("No batch generated yet. Set a seed and click **Generate 14-Scene Batch** to create the scene grid.")
else:
    render_settled_grid()
    render_manual_review_queue()
