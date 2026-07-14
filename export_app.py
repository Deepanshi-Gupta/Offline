"""Standalone Streamlit page: Export & Render (§11 of the UI audit).

Built against Hasaballa_Plan.pdf §11 "Export & Render": simultaneous 4K
export across all three ratios (16:9 / 9:16 / 1:1), a format selector, the
three named bitrate presets, a low-res proxy preview per ratio, a render
queue with independent per-ratio progress (one ratio can fail while the
others keep succeeding, per the UX note), a disk-space warning shown
*before* the render starts, and "Open output folder" on completion.

Architecture note: mirrors smart_director_app.py's chained-rerun pattern —
each script run advances every active ratio's progress by one small step,
then reruns while still "running", so Pause is picked up within about one
frame instead of blocking inside a single Python loop. No real encoder is
wired in: progress and the scripted 9:16 first-attempt failure are timed
simulations, and "Open output folder" just shows where the (non-existent)
files would land.

Run with:
    python -m streamlit run export_app.py
"""

import time

import streamlit as st

from common.scenes import scene_paths
from common.style import image_to_data_uri

st.set_page_config(page_title="Export & Render", layout="centered")

RATIOS = ["16:9", "9:16", "1:1"]
RATIO_ASPECT = {"16:9": "16/9", "9:16": "9/16", "1:1": "1/1"}
FORMATS = ["MP4", "MOV", "WebM"]
BITRATE_PRESETS = {
    "YouTube 4K": {"est_gb": 18, "note": "45 Mbps video / 384 kbps audio"},
    "Instagram": {"est_gb": 10, "note": "25 Mbps video / 256 kbps audio"},
    "WhatsApp": {"est_gb": 3, "note": "8 Mbps video / 128 kbps audio"},
}
FREE_DISK_GB = 38  # deliberately low so the disk-space warning is reachable by default
FAIL_RATIO = "9:16"  # scripted to fail once so per-ratio Failed→Retry is always reachable
FAIL_AT = 0.45

STATUS_STYLE = {
    "not_started": ("#F1F2F4", "#6B6E76", "Not Started"),
    "queued": ("#EEF0F3", "#46484E", "Queued"),
    "rendering": ("#E8F0FE", "#1A56DB", "Rendering…"),
    "paused": ("#FCEFD8", "#7A4E00", "Paused"),
    "complete": ("#E3F7EA", "#187A43", "Complete"),
    "failed": ("#FDECEC", "#B42318", "Failed"),
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

    .proxy-frame {
        border-radius: 10px; overflow: hidden; background: #101114; position: relative;
    }
    .proxy-frame img { width: 100%; height: 100%; object-fit: cover; display: block; opacity: 0.85; }
    .proxy-label {
        position: absolute; bottom: 6px; left: 6px; background: rgba(0,0,0,0.6); color: #fff;
        font-size: 0.72rem; font-weight: 700; padding: 2px 8px; border-radius: 6px;
    }

    .disk-warning {
        background: #FDECEC; border: 1px solid #F5C2BE; color: #8C1D12;
        border-radius: 12px; padding: 0.9rem 1.1rem; margin: 0.6rem 0; font-size: 0.9rem;
    }

    .status-badge {
        display: inline-flex; align-items: center; gap: 6px; font-size: 0.85rem;
        font-weight: 700; padding: 3px 12px; border-radius: 999px;
    }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("export_ratios", {r: True for r in RATIOS})
    st.session_state.setdefault("export_format", "MP4")
    st.session_state.setdefault("bitrate_preset", "YouTube 4K")
    st.session_state.setdefault("burn_in", True)
    st.session_state.setdefault("mixdown", True)
    st.session_state.setdefault("proceed_anyway", False)
    st.session_state.setdefault("queue", None)  # None = idle, never started
    st.session_state.setdefault("overall_status", "idle")  # idle | running | paused | done


_init_state()


def selected_ratios():
    return [r for r in RATIOS if st.session_state.export_ratios[r]]


def estimated_gb():
    per_ratio = BITRATE_PRESETS[st.session_state.bitrate_preset]["est_gb"]
    return per_ratio * len(selected_ratios())


def start_export():
    st.session_state.queue = {
        r: {"status": "queued", "progress": 0.0, "attempts": 0} for r in selected_ratios()
    }
    st.session_state.overall_status = "running"


def advance_tick():
    queue = st.session_state.queue
    for i, (ratio, item) in enumerate(queue.items()):
        if item["status"] == "queued":
            item["status"] = "rendering"
            continue
        if item["status"] != "rendering":
            continue
        step = 0.05 + i * 0.015
        if ratio == FAIL_RATIO and item["attempts"] == 0:
            item["progress"] = min(FAIL_AT, item["progress"] + step)
            if item["progress"] >= FAIL_AT:
                item["status"] = "failed"
                item["attempts"] += 1
            continue
        item["progress"] = min(1.0, item["progress"] + step)
        if item["progress"] >= 1.0:
            item["status"] = "complete"

    if all(item["status"] in ("complete", "failed") for item in queue.values()):
        st.session_state.overall_status = "done"


def status_badge_html(status):
    bg, fg, label = STATUS_STYLE[status]
    return f'<span class="status-badge" style="background:{bg};color:{fg};">{label}</span>'


# =========================================================
# ADVANCE STATE
# =========================================================
if st.session_state.overall_status == "running":
    advance_tick()

# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.2])
with h1:
    st.markdown('<div class="page-title">Export &amp; Render</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.4rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline — local encoder</span></div>',
        unsafe_allow_html=True,
    )
st.caption("Simultaneous multi-ratio 4K export. No real encoder is wired in — this simulates timing and a per-ratio failure.")

st.markdown("<hr>", unsafe_allow_html=True)

locked = st.session_state.overall_status in ("running", "paused")

# =========================================================
# EXPORT SETTINGS
# =========================================================
st.markdown('<div class="section-label">⚙️ Export Settings</div>', unsafe_allow_html=True)

st.markdown("**Ratios (all export simultaneously, each at full 4K)**")
rcols = st.columns(len(RATIOS))
for i, r in enumerate(RATIOS):
    with rcols[i]:
        st.session_state.export_ratios[r] = st.checkbox(r, value=st.session_state.export_ratios[r], key=f"ratio_{r}", disabled=locked)

scol1, scol2 = st.columns(2)
with scol1:
    st.session_state.export_format = st.selectbox("Format", options=FORMATS, index=FORMATS.index(st.session_state.export_format), key="format_select", disabled=locked)
with scol2:
    st.session_state.bitrate_preset = st.selectbox(
        "Bitrate preset", options=list(BITRATE_PRESETS.keys()),
        index=list(BITRATE_PRESETS.keys()).index(st.session_state.bitrate_preset), key="bitrate_select", disabled=locked,
    )
st.caption(BITRATE_PRESETS[st.session_state.bitrate_preset]["note"])

tcol1, tcol2 = st.columns(2)
with tcol1:
    st.session_state.burn_in = st.toggle("Burn-in subtitles", value=st.session_state.burn_in, key="burn_in_toggle", disabled=locked)
with tcol2:
    st.session_state.mixdown = st.toggle("Mix audio down to stereo master", value=st.session_state.mixdown, key="mixdown_toggle", disabled=locked)

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# LOW-RES PROXY PREVIEW
# =========================================================
st.markdown('<div class="section-label">🖼️ Proxy Preview (¼ res)</div>', unsafe_allow_html=True)
scenes = scene_paths()
if selected_ratios():
    pcols = st.columns(len(selected_ratios()))
    for i, r in enumerate(selected_ratios()):
        with pcols[i]:
            uri = image_to_data_uri(scenes[i % len(scenes)])
            st.markdown(
                f'<div class="proxy-frame" style="aspect-ratio:{RATIO_ASPECT[r]};">'
                f'<img src="{uri}" /><span class="proxy-label">{r}</span></div>',
                unsafe_allow_html=True,
            )
else:
    st.info("Select at least one ratio to preview.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# DISK SPACE + START
# =========================================================
est_gb = estimated_gb()
over_budget = est_gb > FREE_DISK_GB
st.markdown(f"**Estimated export size:** ~{est_gb} GB across {len(selected_ratios())} ratio(s) · **Free disk space:** {FREE_DISK_GB} GB")

if over_budget and st.session_state.overall_status == "idle":
    st.markdown(
        f'<div class="disk-warning">⚠ Not enough free disk space — this export needs ~{est_gb} GB but only '
        f"{FREE_DISK_GB} GB is free. Free up space, reduce the number of ratios, or proceed at your own risk.</div>",
        unsafe_allow_html=True,
    )
    st.session_state.proceed_anyway = st.checkbox("Proceed anyway (export may fail partway through)", value=st.session_state.proceed_anyway, key="proceed_checkbox")

start_disabled = (not selected_ratios()) or (over_budget and not st.session_state.proceed_anyway)

if st.session_state.overall_status == "idle":
    if st.button("▶ Start Export", type="primary", key="start_export_btn", width="stretch", disabled=start_disabled):
        start_export()
        st.rerun()

elif st.session_state.overall_status == "running":
    if st.button("⏸ Pause All", key="pause_btn", width="stretch"):
        st.session_state.overall_status = "paused"
        st.rerun()

elif st.session_state.overall_status == "paused":
    if st.button("▶ Resume", type="primary", key="resume_btn", width="stretch"):
        st.session_state.overall_status = "running"
        st.rerun()

elif st.session_state.overall_status == "done":
    ccol1, ccol2 = st.columns(2)
    with ccol1:
        if st.button("📂 Open Output Folder", key="open_folder_btn", width="stretch"):
            st.toast("Opened: exports/hasaballa_project_01/")
    with ccol2:
        if st.button("🔄 Start New Export", key="new_export_btn", width="stretch"):
            st.session_state.queue = None
            st.session_state.overall_status = "idle"
            st.rerun()

# =========================================================
# RENDER QUEUE — independent per-ratio progress
# =========================================================
if st.session_state.queue:
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown('<div class="section-label">📋 Render Queue</div>', unsafe_allow_html=True)
    for r, item in st.session_state.queue.items():
        with st.container(border=True):
            hcol1, hcol2 = st.columns([2, 1])
            with hcol1:
                st.markdown(f"**{r}** · {st.session_state.export_format} · {st.session_state.bitrate_preset}")
            with hcol2:
                st.markdown(status_badge_html(item["status"]), unsafe_allow_html=True)
            st.progress(item["progress"], text=f"{item['progress'] * 100:.0f}%")
            if item["status"] == "failed":
                st.error(f"{r} failed during encoding — the other ratios are unaffected and keep rendering.")
                if st.button(f"↻ Retry {r}", key=f"retry_{r}", type="primary", width="stretch"):
                    item["status"] = "queued"
                    item["progress"] = 0.0
                    st.session_state.overall_status = "running"
                    st.rerun()

st.write("")

# =========================================================
# AUTO-CONTINUE
# =========================================================
if st.session_state.overall_status == "running":
    time.sleep(0.12)
    st.rerun()
