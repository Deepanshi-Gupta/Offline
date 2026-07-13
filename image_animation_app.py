"""Standalone Streamlit page: Image Animation.

Run with:
    streamlit run image_animation_app.py
"""

import streamlit as st

from common.style import (
    face_paths,
    image_to_data_uri,
    inject_base_css,
    thumb_html,
)

st.set_page_config(page_title="Image Animation", layout="centered")
inject_base_css()

if "selected_face" not in st.session_state:
    st.session_state.selected_face = 1
if "voice_assigned" not in st.session_state:
    st.session_state.voice_assigned = set()

faces = face_paths()

st.markdown('<div class="page-title">Image Animation</div>', unsafe_allow_html=True)

st.text_area(
    "Description",
    placeholder="Describe the animation...",
    label_visibility="collapsed",
    height=90,
)

t1, t2, t3 = st.columns(3)
with t1:
    st.toggle("Full Body Animation", value=False, key="full_body")
with t2:
    st.toggle("Background Motion", value=False, key="bg_motion")
with t3:
    st.toggle("Lip Sync", value=True, key="lip_sync")

st.markdown('<div class="section-label">Face Detection</div>', unsafe_allow_html=True)

face_cols = st.columns(6)
for i, col in enumerate(faces, start=1):
    with face_cols[i - 1]:
        data_uri = image_to_data_uri(col)
        is_selected = st.session_state.selected_face == i
        st.markdown(thumb_html(data_uri, selected=is_selected), unsafe_allow_html=True)
        if i <= 5:
            if st.button(f"Face {i}", key=f"face_btn_{i}", use_container_width=True):
                st.session_state.selected_face = i
        else:
            st.markdown("&nbsp;", unsafe_allow_html=True)

st.markdown('<div class="section-label">Assign Voice to Face</div>', unsafe_allow_html=True)

voice_cols = st.columns(6)
for i in range(1, 7):
    with voice_cols[i - 1]:
        st.markdown('<div class="voice-icon-btn">', unsafe_allow_html=True)
        assigned = i in st.session_state.voice_assigned
        label = "✓" if assigned else "⬇"
        if st.button(label, key=f"voice_btn_{i}", use_container_width=True):
            st.session_state.voice_assigned.symmetric_difference_update({i})
        st.markdown("</div>", unsafe_allow_html=True)

st.write("")
b1, spacer, b2 = st.columns([1.3, 2.4, 1.5])
with b1:
    st.button("⏭️  Skip", key="skip_btn", use_container_width=True)
with b2:
    st.button("Generate Video", type="primary", key="generate_video_btn", use_container_width=True)
