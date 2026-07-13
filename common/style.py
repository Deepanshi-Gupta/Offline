"""Shared CSS + small helpers reused by both standalone Streamlit pages."""

import base64
from pathlib import Path

import streamlit as st

ASSETS_DIR = Path(__file__).parent.parent / "assets"


def image_to_data_uri(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode()
    return f"data:image/png;base64,{encoded}"


def face_paths():
    return sorted((ASSETS_DIR / "faces").glob("face_*.png"), key=lambda p: int(p.stem.split("_")[1]))


def reference_paths():
    return sorted((ASSETS_DIR / "references").glob("ref_*.png"), key=lambda p: int(p.stem.split("_")[1]))


def inject_base_css(card: bool = True):
    card_css = (
        """
        .block-container {
            background: #FFFFFF;
            border: 1px solid #E6E7EA;
            border-radius: 18px;
            box-shadow: 0 2px 10px rgba(20, 20, 30, 0.04);
            margin-top: 2rem;
        }
        """
        if card
        else ""
    )
    st.markdown(
        """
        <style>
        #MainMenu, header, footer {visibility: hidden;}

        .block-container {
            max-width: 900px;
            padding: 2.25rem 2.5rem 2rem 2.5rem;
        }
        __CARD_CSS__

        .page-title {
            font-size: 2rem;
            font-weight: 800;
            text-align: center;
            margin-bottom: 1.25rem;
            color: #101114;
        }

        .section-label {
            font-weight: 700;
            font-size: 1.02rem;
            color: #17181B;
            margin: 0.9rem 0 0.6rem 0;
        }

        div[data-testid="stTextArea"] textarea {
            border-radius: 12px;
            border: 1px solid #DDDFE3;
            font-size: 0.95rem;
        }

        div[data-testid="stCheckbox"] {
            justify-content: flex-end;
        }

        /* toggle switch label styling to match bold sans headers */
        div[data-testid="stToggle"] label p {
            font-weight: 700;
            font-size: 0.98rem;
            color: #17181B;
        }

        /* face / reference thumbnail card */
        .thumb-wrap {
            position: relative;
            border-radius: 14px;
            overflow: hidden;
            border: 3px solid transparent;
            aspect-ratio: 1 / 1;
        }
        .thumb-wrap img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }
        .thumb-wrap.selected {
            border: 3px dashed #1A1A1A;
        }
        .mic-badge {
            position: absolute;
            bottom: 6px;
            left: 6px;
            width: 26px;
            height: 26px;
            border-radius: 50%;
            background: rgba(20, 20, 20, 0.72);
            color: #fff;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 13px;
        }

        .ref-thumb {
            border-radius: 12px;
            overflow: hidden;
            aspect-ratio: 5 / 3;
        }
        .ref-thumb img {
            width: 100%;
            height: 100%;
            object-fit: cover;
            display: block;
        }

        .face-caption {
            text-align: center;
            font-size: 0.85rem;
            color: #333;
            margin-top: 0.3rem;
        }

        /* generic buttons */
        div[data-testid="stButton"] button {
            border-radius: 10px;
            font-weight: 600;
        }
        div[data-testid="stButton"] button[kind="primary"] {
            background-color: #2F6FEF;
            border: none;
        }
        div[data-testid="stButton"] button[kind="secondary"] {
            background-color: #F1F2F4;
            border: 1px solid #E1E2E6;
            color: #26272B;
        }

        .voice-icon-btn button {
            padding: 0.35rem 0 !important;
            font-size: 1rem !important;
        }
        </style>
        """.replace("__CARD_CSS__", card_css),
        unsafe_allow_html=True,
    )


def inject_gray_canvas_css():
    st.markdown(
        """
        <style>
        .stApp {
            background-color: #E9E9EB;
        }
        .aspect-btn-row div[data-testid="stButton"] button {
            border-radius: 8px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def thumb_html(data_uri: str, selected: bool = False, show_mic: bool = True) -> str:
    cls = "thumb-wrap selected" if selected else "thumb-wrap"
    mic = '<div class="mic-badge">&#127908;</div>' if show_mic else ""
    return f'<div class="{cls}"><img src="{data_uri}" />{mic}</div>'


def ref_thumb_html(data_uri: str) -> str:
    return f'<div class="ref-thumb"><img src="{data_uri}" /></div>'
