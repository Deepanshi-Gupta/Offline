"""Standalone Streamlit page: Publishing (§15 of the UI audit) — the ONLY
online surface in the platform.

Built against Hasaballa_Plan.pdf §15: because the app is offline by
default, per the UX note the upload screen's default state is
"offline / unavailable" and that is designed first, not the OAuth flow.
Going online is a deliberate action taken on the Settings screen (§14) —
this page can't flip that switch itself, so a clearly-labelled demo toggle
stands in for "Settings says we're online" so the rest of the flow (OAuth
consent, Arabic metadata upload, retry-on-failure, Published, token
expiry, AdSense/CPM dashboard) is reachable in isolation.

No real Google OAuth or YouTube Data API call is wired in. "Authenticate"
is a simulated consent dialog, and the token is never displayed or stored
in plain text — only a "🔒 stored encrypted" badge is shown. Upload is a
timed simulation with a scripted first-attempt network failure so
Failed → Retry is always reachable.

Run with:
    python -m streamlit run publishing_app.py
"""

import time

import streamlit as st

from common.scenes import scene_paths
from common.style import image_to_data_uri

st.set_page_config(page_title="Publishing", layout="centered")

FAKE_CHANNEL = "Hasaballa Studio"
FAKE_VIDEO_ID = "hb-demo-0142"

st.markdown(
    """
    <style>
    #MainMenu, header, footer {visibility: hidden;}
    .block-container { max-width: 950px; padding: 2rem 2.25rem; }

    .page-title { font-size: 2rem; font-weight: 800; color: #101114; margin-bottom: 0; }
    .offline-pill, .online-pill {
        display: inline-flex; align-items: center; gap: 6px;
        border-radius: 999px; padding: 3px 12px; font-size: 0.8rem; font-weight: 600;
    }
    .offline-pill { background: #F1F2F4; color: #46484E; border: 1px solid #E1E2E6; }
    .online-pill { background: #FDECEC; color: #8C1D12; border: 1px solid #F5C2BE; }
    .section-label { font-weight: 700; font-size: 1.05rem; margin: 1rem 0 0.5rem 0; }

    .rtl-input input, .rtl-textarea textarea {
        direction: rtl; text-align: right; border-radius: 10px; border: 1px solid #DDDFE3;
    }

    .secure-badge {
        display: inline-flex; align-items: center; gap: 6px; font-size: 0.78rem; font-weight: 700;
        color: #187A43; background: #E3F7EA; border-radius: 999px; padding: 2px 10px;
    }
    .stat-tile {
        background: #F7F8FA; border: 1px solid #E6E7EA; border-radius: 12px;
        padding: 0.8rem 1rem; text-align: center;
    }
    .stat-tile .val { font-size: 1.4rem; font-weight: 800; color: #101114; }
    .stat-tile .lbl { font-size: 0.78rem; color: #6B6E76; font-weight: 600; }

    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


def _init_state():
    st.session_state.setdefault("pub_connection", "offline")  # demo stand-in for §14's global state
    st.session_state.setdefault("auth_status", "not_authenticated")  # not_authenticated | authenticating | authenticated | token_expired
    st.session_state.setdefault("upload_status", "idle")  # idle | uploading | failed | published
    st.session_state.setdefault("upload_progress", 0.0)
    st.session_state.setdefault("upload_attempts", 0)
    st.session_state.setdefault("title_ar", "قصة من الصحراء")
    st.session_state.setdefault("desc_ar", "فيلم قصير من إنتاج منصة حصبلة الذكية.")
    st.session_state.setdefault("tags_ar", "قصة, صحراء, تراث")
    st.session_state.setdefault("privacy", "Public")


_init_state()


@st.dialog("Sign in with Google — Consent")
def oauth_consent_dialog():
    st.markdown(f"**{FAKE_CHANNEL}** is requesting the following YouTube Data API v3 permissions:")
    st.markdown("- Upload and manage your videos\n- View your channel's basic info\n- View channel analytics (AdSense/CPM)")
    st.caption("Your token is stored encrypted on this machine — never in plain text — and only used for publishing actions you initiate.")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Allow", type="primary", key="oauth_allow_btn", width="stretch"):
            st.session_state.auth_status = "authenticating"
            st.rerun()
    with c2:
        if st.button("Deny", key="oauth_deny_btn", width="stretch"):
            st.rerun()


def run_upload():
    attempts = st.session_state.upload_attempts
    progress = st.progress(0.0, text="Uploading…")
    for pct in (0.2, 0.4, 0.6):
        time.sleep(0.3)
        progress.progress(pct, text="Uploading…")
        if attempts == 0 and pct == 0.6:
            st.session_state.upload_status = "failed"
            st.session_state.upload_attempts += 1
            return
    for pct in (0.8, 1.0):
        time.sleep(0.3)
        progress.progress(pct, text="Uploading…")
    st.session_state.upload_status = "published"
    st.session_state.upload_attempts += 1


# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.3])
with h1:
    st.markdown('<div class="page-title">Publishing</div>', unsafe_allow_html=True)
with h2:
    online = st.session_state.pub_connection == "online"
    pill = '<span class="online-pill">🌐 Online</span>' if online else '<span class="offline-pill">🔒 Offline</span>'
    st.markdown(f'<div style="text-align:right;margin-top:0.4rem;">{pill}</div>', unsafe_allow_html=True)
st.caption("The only screen in the platform that uses the internet. No real Google OAuth or YouTube API call is wired in.")

st.markdown("<hr>", unsafe_allow_html=True)

# =========================================================
# OFFLINE — DEFAULT, DESIGNED FIRST
# =========================================================
if st.session_state.pub_connection == "offline":
    st.info(
        "📴 **Publishing is unavailable while offline** — this is the expected default state. "
        "Go to **Settings (§14) → Smart Internet Access** and explicitly allow internet access to publish."
    )
    st.write("")
    if st.button("🔧 Demo: simulate internet available (normally set in Settings §14)", key="demo_online_btn"):
        st.session_state.pub_connection = "online"
        st.rerun()
    st.stop()

dcol1, dcol2 = st.columns([3, 1])
with dcol2:
    if st.button("🔧 Demo: go offline", key="demo_offline_btn", width="stretch"):
        st.session_state.pub_connection = "offline"
        st.session_state.auth_status = "not_authenticated"
        st.session_state.upload_status = "idle"
        st.rerun()

# =========================================================
# AUTHENTICATION
# =========================================================
st.markdown('<div class="section-label">🔐 YouTube Account</div>', unsafe_allow_html=True)

if st.session_state.auth_status == "not_authenticated":
    st.write("Not authenticated.")
    if st.button("Sign in with Google", type="primary", key="signin_btn"):
        oauth_consent_dialog()

elif st.session_state.auth_status == "authenticating":
    with st.spinner("Authenticating…"):
        time.sleep(0.6)
    st.session_state.auth_status = "authenticated"
    st.rerun()

elif st.session_state.auth_status == "token_expired":
    st.warning("Your session has expired. Please sign in again to continue publishing.")
    if st.button("Sign in with Google", type="primary", key="reauth_btn"):
        oauth_consent_dialog()

elif st.session_state.auth_status == "authenticated":
    acol1, acol2 = st.columns([3, 1.2])
    with acol1:
        st.success(f"Signed in as **{FAKE_CHANNEL}**")
        st.markdown('<span class="secure-badge">🔒 Token stored encrypted</span>', unsafe_allow_html=True)
    with acol2:
        if st.button("Simulate token expiry", key="expire_btn", width="stretch"):
            st.session_state.auth_status = "token_expired"
            st.rerun()
    st.caption("Demo control above — normally tokens expire silently in the background and this state appears on the next publish attempt.")

st.markdown("<hr>", unsafe_allow_html=True)

if st.session_state.auth_status != "authenticated":
    st.info("Sign in above to upload.")
    st.stop()

# =========================================================
# UPLOAD FORM
# =========================================================
st.markdown('<div class="section-label">⬆️ Upload to YouTube</div>', unsafe_allow_html=True)

if st.session_state.upload_status in ("idle", "failed"):
    tcol1, tcol2 = st.columns([2, 1])
    with tcol1:
        with st.container(key="title_rtl"):
            st.markdown('<div class="rtl-input">', unsafe_allow_html=True)
            st.session_state.title_ar = st.text_input("Title (Arabic)", value=st.session_state.title_ar, key="title_input")
            st.markdown("</div>", unsafe_allow_html=True)
        with st.container(key="desc_rtl"):
            st.markdown('<div class="rtl-textarea">', unsafe_allow_html=True)
            st.session_state.desc_ar = st.text_area("Description (Arabic)", value=st.session_state.desc_ar, key="desc_input", height=90)
            st.markdown("</div>", unsafe_allow_html=True)
        with st.container(key="tags_rtl"):
            st.markdown('<div class="rtl-input">', unsafe_allow_html=True)
            st.session_state.tags_ar = st.text_input("Tags (comma-separated, Arabic)", value=st.session_state.tags_ar, key="tags_input")
            st.markdown("</div>", unsafe_allow_html=True)
        st.session_state.privacy = st.selectbox("Privacy", options=["Public", "Unlisted", "Private"], index=["Public", "Unlisted", "Private"].index(st.session_state.privacy), key="privacy_select")
    with tcol2:
        scenes = scene_paths()
        st.image(image_to_data_uri(scenes[0]), width="stretch", caption="Thumbnail")

    if st.session_state.upload_status == "failed":
        st.error("Upload failed — network connection was interrupted partway through.")
        if st.button("↻ Retry Upload", type="primary", key="retry_upload_btn", width="stretch"):
            run_upload()
            st.rerun()
    else:
        if st.button("⬆ Upload to YouTube", type="primary", key="upload_btn", width="stretch"):
            run_upload()
            st.rerun()

elif st.session_state.upload_status == "published":
    st.success(f"✅ Published! **{st.session_state.title_ar}**")
    st.code(f"https://youtube.com/watch?v={FAKE_VIDEO_ID}", language=None)
    if st.button("📤 Publish Another Video", key="publish_another_btn"):
        st.session_state.upload_status = "idle"
        st.session_state.upload_attempts = 0
        st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    # =========================================================
    # ADSENSE / ANALYTICS DASHBOARD
    # =========================================================
    st.markdown('<div class="section-label">💰 Revenue &amp; Analytics</div>', unsafe_allow_html=True)
    scol1, scol2, scol3, scol4 = st.columns(4)
    for col, (val, lbl) in zip(
        (scol1, scol2, scol3, scol4),
        [("$142.30", "Est. Revenue"), ("$3.85", "CPM"), ("12,480", "Views"), ("612 hrs", "Watch Time")],
    ):
        with col:
            st.markdown(f'<div class="stat-tile"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)
    st.write("")
    st.caption("Views — last 7 days")
    st.bar_chart({"Views": [820, 1140, 990, 1560, 2010, 2430, 3530]})
