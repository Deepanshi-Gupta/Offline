"""Standalone Streamlit page: Character Pack Manager (§4 of the UI audit).

Built against Hasaballa_Plan.pdf §4 "Character Pack Manager": a character
list with 8 reference-image slots per character, per-image weighting,
image↔voice pairing, JSON import/export, and identity-conflict detection.

Identity-conflict detection here is a real (if simple) implementation: it
hashes each uploaded reference image and flags a character if two slots
contain the byte-identical file — a stand-in for the real face-embedding
similarity check the production app would run.

Run with:
    python -m streamlit run character_pack_manager_app.py
"""

import base64
import hashlib
import json

import streamlit as st

from common.style import face_paths
from common.voices import VOICES

st.set_page_config(page_title="Character Pack Manager", layout="centered")

FACE_PATHS = face_paths()
VOICE_NAMES = [f"{v['icon']} {v['name']}" for v in VOICES]
SLOTS_PER_CHARACTER = 8

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

    .status-badge {
        display: inline-flex; align-items: center; gap: 6px; font-size: 0.82rem;
        font-weight: 700; padding: 2px 10px; border-radius: 999px;
    }

    .avatar-placeholder {
        aspect-ratio: 1/1; border-radius: 10px; background: #EEF0F3;
        display: flex; align-items: center; justify-content: center;
        font-size: 2.2rem; color: #B7BAC1; border: 1px solid #E2E4E8;
    }
    .empty-slot {
        aspect-ratio: 1/1; border-radius: 10px; background: #F7F8FA;
        border: 2px dashed #D7D9DE; display: flex; align-items: center;
        justify-content: center; font-size: 0.85rem; color: #8A8D94; text-align: center;
    }
    div[data-testid="stButton"] button { border-radius: 8px; font-weight: 600; }
    div[data-testid="stButton"] button[kind="primary"] { background-color: #2F6FEF; border: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

STATUS_STYLE = {
    "empty": ("#F1F2F4", "#6B6E76", "No images yet"),
    "incomplete": ("#FCEFD8", "#9A6B00", "Incomplete"),
    "complete": ("#E3F7EA", "#187A43", "Complete"),
    "conflict": ("#FDECEC", "#B42318", "Identity conflict"),
}


def status_badge_html(status: str) -> str:
    bg, fg, label = STATUS_STYLE[status]
    return f'<span class="status-badge" style="background:{bg};color:{fg};">{label}</span>'


def image_hash(data: bytes | None):
    return hashlib.sha256(data).hexdigest() if data else None


def find_conflict_pairs(images):
    seen, pairs = {}, []
    for i, im in enumerate(images):
        if im is None:
            continue
        h = image_hash(im)
        if h in seen:
            pairs.append((seen[h], i))
        else:
            seen[h] = i
    return pairs


def character_status(char):
    filled = sum(1 for im in char["images"] if im is not None)
    conflict = bool(find_conflict_pairs(char["images"]))
    if conflict:
        return "conflict", filled
    if filled == 0:
        return "empty", filled
    if filled < SLOTS_PER_CHARACTER:
        return "incomplete", filled
    return "complete", filled


def _demo_image_bytes(idx: int) -> bytes:
    return FACE_PATHS[idx % len(FACE_PATHS)].read_bytes()


def _new_character(name, filled=0, dup_slots=None, voice_idx=0):
    images = [None] * SLOTS_PER_CHARACTER
    weights = [1.0] * SLOTS_PER_CHARACTER
    for i in range(filled):
        images[i] = _demo_image_bytes(i)
    if dup_slots:
        a, b = dup_slots
        images[b] = images[a]
    return {"name": name, "voice_idx": voice_idx, "images": images, "weights": weights}


def _init_state():
    if "characters" not in st.session_state:
        st.session_state.characters = [
            _new_character("Layla", filled=8, dup_slots=(0, 4), voice_idx=3),
            _new_character("Omar", filled=3, voice_idx=0),
        ]
    st.session_state.setdefault("editing_idx", None)


_init_state()

# =========================================================
# HEADER
# =========================================================
h1, h2 = st.columns([3, 1.2])
with h1:
    st.markdown('<div class="page-title">Character Pack Manager</div>', unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div style="text-align:right;margin-top:0.4rem;">'
        '<span class="offline-pill"><span class="dot"></span>Offline — no network used</span></div>',
        unsafe_allow_html=True,
    )
st.caption("8 reference images per character, per-image weighting, and a paired voice — matches JSON import/export.")

# =========================================================
# LIST VIEW
# =========================================================
if st.session_state.editing_idx is None:
    t1, t2, t3 = st.columns([1.3, 1.3, 1.3])
    with t1:
        if st.button("+ Add Character", type="primary", key="add_char", width="stretch"):
            st.session_state.characters.append(
                _new_character(f"Character {len(st.session_state.characters) + 1}")
            )
            st.rerun()
    with t2:
        import_file = st.file_uploader(
            "Import JSON", type=["json"], label_visibility="collapsed", key="import_json"
        )
        if import_file is not None:
            try:
                data = json.loads(import_file.getvalue())
                chars = [
                    {
                        "name": c["name"],
                        "voice_idx": c["voice_idx"],
                        "weights": c["weights"],
                        "images": [base64.b64decode(im) if im else None for im in c["images"]],
                    }
                    for c in data
                ]
                st.session_state.characters = chars
                st.success(f"Imported {len(chars)} character(s).")
            except Exception as e:
                st.error(f"Import failed — invalid character pack JSON: {e}")
    with t3:
        export_payload = json.dumps(
            [
                {
                    "name": c["name"],
                    "voice_idx": c["voice_idx"],
                    "weights": c["weights"],
                    "images": [base64.b64encode(im).decode() if im else None for im in c["images"]],
                }
                for c in st.session_state.characters
            ]
        )
        st.download_button(
            "⬇ Export JSON",
            data=export_payload,
            file_name="character_pack.json",
            mime="application/json",
            key="export_json",
            width="stretch",
        )

    st.write("")

    if not st.session_state.characters:
        st.info("No characters yet — click **+ Add Character** to create your first character pack.")
    else:
        cols = st.columns(3)
        for i, char in enumerate(st.session_state.characters):
            status, filled = character_status(char)
            with cols[i % 3]:
                with st.container(border=True):
                    thumb = next((im for im in char["images"] if im), None)
                    if thumb:
                        st.image(thumb, width="stretch")
                    else:
                        st.markdown('<div class="avatar-placeholder">👤</div>', unsafe_allow_html=True)
                    st.markdown(f"**{char['name']}**")
                    st.markdown(
                        f'{status_badge_html(status)} &nbsp; {filled}/{SLOTS_PER_CHARACTER} images',
                        unsafe_allow_html=True,
                    )
                    if status == "conflict":
                        pairs = find_conflict_pairs(char["images"])
                        a, b = pairs[0]
                        st.warning(f"⚠ Slots {a + 1} and {b + 1} use the identical image.")
                    st.caption(f"Voice: {VOICE_NAMES[char['voice_idx']]}")
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        if st.button("Edit", key=f"edit_{i}", width="stretch"):
                            st.session_state.editing_idx = i
                            st.rerun()
                    with ec2:
                        if st.button("Remove", key=f"remove_{i}", width="stretch"):
                            st.session_state.characters.pop(i)
                            st.rerun()

# =========================================================
# EDITOR VIEW
# =========================================================
else:
    idx = st.session_state.editing_idx
    char = st.session_state.characters[idx]

    if st.button("← Back to Character List", key="back_btn"):
        st.session_state.editing_idx = None
        st.rerun()

    n1, n2 = st.columns([2, 1.4])
    with n1:
        char["name"] = st.text_input("Character name", value=char["name"], key=f"name_{idx}")
    with n2:
        char["voice_idx"] = st.selectbox(
            "Paired voice",
            options=range(len(VOICE_NAMES)),
            format_func=lambda i: VOICE_NAMES[i],
            index=char["voice_idx"],
            key=f"voice_{idx}",
        )

    status, filled = character_status(char)
    st.markdown(
        f'{status_badge_html(status)} &nbsp; {filled}/{SLOTS_PER_CHARACTER} reference images',
        unsafe_allow_html=True,
    )
    if status == "conflict":
        for a, b in find_conflict_pairs(char["images"]):
            st.warning(f"⚠ Identity conflict: slots {a + 1} and {b + 1} use the identical image.")

    st.markdown("**Reference Images (8 slots)**")
    for row_start in (0, 4):
        cols = st.columns(4)
        for c in range(4):
            slot = row_start + c
            with cols[c]:
                with st.container(border=True):
                    if char["images"][slot] is not None:
                        st.image(char["images"][slot], width="stretch")
                        char["weights"][slot] = st.slider(
                            "Weight",
                            0.0,
                            1.0,
                            value=char["weights"][slot],
                            key=f"weight_{idx}_{slot}",
                            label_visibility="collapsed",
                        )
                        st.caption(f"Slot {slot + 1} · weight {char['weights'][slot]:.2f}")
                        if st.button("Remove", key=f"rm_img_{idx}_{slot}", width="stretch"):
                            char["images"][slot] = None
                            st.rerun()
                    else:
                        st.markdown(f'<div class="empty-slot">+ Slot {slot + 1}</div>', unsafe_allow_html=True)
                        upl = st.file_uploader(
                            f"slot {slot}",
                            type=["png", "jpg", "jpeg"],
                            label_visibility="collapsed",
                            key=f"upl_{idx}_{slot}",
                        )
                        if upl is not None:
                            char["images"][slot] = upl.getvalue()
                            st.rerun()
