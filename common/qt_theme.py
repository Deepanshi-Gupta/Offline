"""Palette tokens and base QSS for the Smart Internet Access panel — a
direct port of the HTML/CSS mockup's custom-property token system to
Python dicts, kept under the same names so the two stay easy to compare.

Per-state colors (hero banner / badge / handoff block) are looked up at
runtime from PALETTES[theme][state] rather than baked into static QSS,
because each combination is a plain color swap, not a structural change —
see smart_internet_access_qt.py's _render_state().
"""

FONT_FAMILY = "Tajawal Medium"
FONT_FAMILY_BOLD = "Tajawal ExtraBold"

# App-wide design tokens shared by every converted screen — lifted directly
# from the hex values repeated across every *_app.py Streamlit source file,
# so converted screens stay visually identical rather than drifting toward
# a new palette per screen.
SEMANTIC = {
    "light": {
        "primary": "#2F6FEF",
        "success_fg": "#187A43",
        "success_fg_strong": "#146134",
        "success_bg": "#E3F7EA",
        "success_border": "#BEE8CC",
        "warning_fg": "#9A6B00",
        "warning_fg_strong": "#7A4E00",
        "warning_bg": "#FFF6E5",
        "warning_border": "#F0E2BC",
        "danger_fg": "#B42318",
        "danger_fg_strong": "#8C1D12",
        "danger_bg": "#FDECEC",
        "danger_border": "#F5C2BE",
        "info_fg": "#1A56DB",
        "info_bg": "#E8F0FE",
        "info_border": "#C7DBFC",
        "ink": "#101114",
        "ink_soft": "#46484E",
        "ink_faint": "#6B6E76",
        "ink_fainter": "#8A8D94",
        "border": "#E2E4E8",
        "border_soft": "#E6E7EA",
        "surface": "#FFFFFF",
        "surface_soft": "#F7F8FA",
        "surface_muted": "#EEF0F3",
        "surface_input": "#F1F2F4",
        "dashed_border": "#D7D9DE",
    },
    "dark": {
        "primary": "#5C8DFF",
        "success_fg": "#4fd68b",
        "success_fg_strong": "#6fe3a2",
        "success_bg": "#123423",
        "success_border": "#1f5138",
        "warning_fg": "#f0ad4a",
        "warning_fg_strong": "#f7c069",
        "warning_bg": "#3a2a0f",
        "warning_border": "#5c4319",
        "danger_fg": "#ef6a5e",
        "danger_fg_strong": "#f68c82",
        "danger_bg": "#3a1613",
        "danger_border": "#5c2621",
        "info_fg": "#7fa6ff",
        "info_bg": "#152036",
        "info_border": "#233257",
        "ink": "#eef1ee",
        "ink_soft": "#c3c9c5",
        "ink_faint": "#9aa1a2",
        "ink_fainter": "#7c837f",
        "border": "#262e29",
        "border_soft": "#232a25",
        "surface": "#171c19",
        "surface_soft": "#1b211d",
        "surface_muted": "#1e2521",
        "surface_input": "#1e2521",
        "dashed_border": "#39433c",
    },
}


def semantic(dark: bool) -> dict:
    return SEMANTIC["dark" if dark else "light"]

PALETTES = {
    "light": {
        "paper": "#f4f6f3",
        "canvas_a": "#eef4ef",
        "canvas_b": "#f6f5f2",
        "card": "#ffffff",
        "card_border": "#e2e6e0",
        "hairline": "#e7eae5",
        "ink": "#14181a",
        "ink_soft": "#5c655f",
        "ink_faint": "#8b938c",
        "a": {"fg": "#157a4a", "fg_strong": "#0f6b3f", "bg": "#e6f5ec", "border": "#bfe4cd", "glow": "#157a4a"},
        "b": {"fg": "#a3620a", "fg_strong": "#8a5307", "bg": "#fdf1dc", "border": "#f2d49b", "glow": "#c5800f"},
        "c": {"fg": "#5347c9", "fg_strong": "#453aad", "bg": "#ecebfb", "border": "#cfc9f3", "glow": "#5347c9"},
    },
    "dark": {
        "paper": "#0f1310",
        "canvas_a": "#101a14",
        "canvas_b": "#14120e",
        "card": "#171c19",
        "card_border": "#262e29",
        "hairline": "#232a25",
        "ink": "#eef1ee",
        "ink_soft": "#a7b2ab",
        "ink_faint": "#6d766f",
        "a": {"fg": "#4fd68b", "fg_strong": "#6fe3a2", "bg": "#123423", "border": "#1f5138", "glow": "#4fd68b"},
        "b": {"fg": "#f0ad4a", "fg_strong": "#f7c069", "bg": "#3a2a0f", "border": "#5c4319", "glow": "#f0ad4a"},
        "c": {"fg": "#a79bff", "fg_strong": "#bcb2ff", "bg": "#221d40", "border": "#362d5e", "glow": "#a79bff"},
    },
}


def palette(dark: bool) -> dict:
    return PALETTES["dark" if dark else "light"]


def build_stylesheet(dark: bool) -> str:
    p = palette(dark)
    s = semantic(dark)
    return f"""
    QWidget {{
        font-family: "{FONT_FAMILY}";
        color: {s['ink']};
    }}
    QMainWindow, #canvas, #appShell {{
        background: {p['paper']};
    }}
    QToolTip {{
        background: {s['surface']};
        color: {s['ink']};
        border: 1px solid {s['border']};
        padding: 4px 8px;
        border-radius: 6px;
    }}

    /* ---- generic app-wide primitives (common/qt_widgets.py) ---- */
    QFrame[role="card"] {{
        background: {s['surface']};
        border: 1px solid {s['border_soft']};
        border-radius: 14px;
    }}
    QFrame[role="cardFlat"] {{
        background: {s['surface_soft']};
        border: 1px solid {s['border']};
        border-radius: 10px;
    }}
    QLabel[role="pageTitle"] {{
        font-family: "{FONT_FAMILY_BOLD}";
        font-size: 22px;
        color: {s['ink']};
    }}
    QLabel[role="sectionLabel"] {{
        font-family: "{FONT_FAMILY_BOLD}";
        font-size: 14px;
        color: {s['ink']};
    }}
    QLabel[role="caption"] {{
        font-size: 11.5px;
        color: {s['ink_fainter']};
    }}
    QFrame[role="emptySlot"] {{
        background: {s['surface_soft']};
        border: 2px dashed {s['dashed_border']};
        border-radius: 10px;
    }}
    QLabel[role="emptySlotLabel"] {{
        color: {s['ink_fainter']};
        font-size: 12px;
    }}

    QPushButton {{
        font-family: "{FONT_FAMILY}";
        border-radius: 9px;
        font-weight: 600;
        padding: 7px 16px;
        border: 1px solid {s['border']};
        background: {s['surface_input']};
        color: {s['ink']};
    }}
    QPushButton:hover {{ background: {s['border']}; }}
    QPushButton:disabled {{ color: {s['ink_fainter']}; background: {s['surface_soft']}; }}
    QPushButton[variant="primary"] {{
        background: {s['primary']};
        border: none;
        color: white;
    }}
    QPushButton[variant="primary"]:hover {{ background: {s['info_fg']}; }}
    QPushButton[variant="primary"]:disabled {{ background: {s['border']}; color: {s['ink_fainter']}; }}
    QPushButton[variant="danger"] {{
        background: {s['danger_bg']};
        border: 1px solid {s['danger_border']};
        color: {s['danger_fg_strong']};
    }}
    QPushButton[variant="danger"]:hover {{ background: {s['danger_border']}; }}
    QPushButton:focus {{ outline: none; border: 1px solid {s['primary']}; }}

    QLineEdit, QTextEdit, QPlainTextEdit {{
        border-radius: 10px;
        border: 1px solid {s['border']};
        background: {s['surface_input']};
        padding: 6px 9px;
        selection-background-color: {s['primary']};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {s['primary']}; }}
    QComboBox {{
        border-radius: 9px;
        border: 1px solid {s['border']};
        background: {s['surface_input']};
        padding: 5px 10px;
    }}
    QSlider::groove:horizontal {{ height: 5px; background: {s['border']}; border-radius: 2px; }}
    QSlider::handle:horizontal {{
        background: {s['primary']}; width: 15px; height: 15px; margin: -6px 0; border-radius: 7px;
    }}
    QSlider::sub-page:horizontal {{ background: {s['primary']}; border-radius: 2px; }}
    QProgressBar {{
        border: none;
        background: {s['surface_muted']};
        border-radius: 6px;
        text-align: center;
        color: {s['ink_soft']};
        font-size: 11px;
        height: 14px;
    }}
    QProgressBar::chunk {{ background: {s['primary']}; border-radius: 6px; }}
    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ width: 10px; background: transparent; }}
    QScrollBar::handle:vertical {{ background: {s['border']}; border-radius: 5px; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

    QToolButton[role="thumb"] {{
        border-radius: 12px;
        border: 3px solid transparent;
        background: {s['surface_muted']};
        padding: 0;
    }}
    QToolButton[role="thumb"]:checked {{
        border: 3px dashed {s['ink']};
    }}

    /* ---- app shell / sidebar ---- */
    #sidebar {{
        background: {s['surface']};
        border-left: 1px solid {s['border_soft']};
    }}
    #sidebarBrand {{
        font-family: "{FONT_FAMILY_BOLD}";
        font-size: 15px;
        color: {s['ink']};
        padding: 6px 0 2px 0;
    }}
    QPushButton[role="navItem"] {{
        text-align: right;
        border: none;
        background: transparent;
        border-radius: 9px;
        padding: 9px 12px;
        font-weight: 600;
        color: {s['ink_soft']};
    }}
    QPushButton[role="navItem"]:hover {{
        background: {s['surface_muted']};
    }}
    QPushButton[role="navItem"]:checked {{
        background: {s['primary']};
        color: white;
    }}
    #panelCard {{
        background: {p['card']};
        border: 1px solid {p['card_border']};
        border-radius: 20px;
    }}
    #panelTitle {{
        font-family: "{FONT_FAMILY_BOLD}";
        font-size: 16px;
        color: {p['ink']};
    }}
    QLabel[class="rowTitle"] {{
        font-size: 13.5px;
        color: {p['ink']};
    }}
    QLabel[class="rowHelp"] {{
        font-size: 11.5px;
        color: {p['ink_faint']};
    }}
    #stageLabel {{
        font-size: 12px;
        color: {p['ink_faint']};
    }}
    #footer {{
        font-size: 11px;
        color: {p['ink_faint']};
        border-top: 1px solid {p['hairline']};
    }}
    QFrame[role="rowIcon"] {{
        background: {p['paper']};
        border: 1px solid {p['hairline']};
        border-radius: 9px;
    }}
    QFrame[role="divider"] {{
        background: {p['hairline']};
        max-height: 1px;
        min-height: 1px;
        border: none;
    }}
    QFrame#toast {{
        background: {p['a']['bg']};
        border: 1px solid {p['a']['border']};
        border-radius: 12px;
    }}
    QFrame#toast QLabel {{
        color: {p['a']['fg_strong']};
        font-size: 12.5px;
        background: transparent;
        border: none;
    }}
    QFrame#statusBadge {{
        border-radius: 999px;
    }}
    QFrame#handoffBlock {{
        border: 1px solid {p['hairline']};
        border-radius: 14px;
        background: transparent;
    }}
    QFrame#handoffBlock[active="true"] {{
        background: {p['c']['bg']};
        border-color: {p['c']['border']};
    }}
    QLabel#heroCopy {{
        font-weight: 500;
    }}
    QPushButton#disconnectBtn {{
        border-radius: 999px;
        padding: 8px 16px;
        font-size: 12.5px;
        border: 1px solid {p['a']['border']};
        background: {p['a']['bg']};
        color: {p['a']['fg_strong']};
    }}
    QPushButton#disconnectBtn:hover {{
        background: {p['a']['border']};
    }}
    QPushButton#disconnectBtn:pressed {{
        background: {p['a']['fg']};
        color: white;
    }}
    QPushButton#themeToggle {{
        border-radius: 8px;
        padding: 6px 12px;
        font-size: 12px;
        border: 1px solid {p['card_border']};
        background: {p['card']};
        color: {p['ink_soft']};
    }}
    QPushButton#themeToggle:hover {{
        background: {p['hairline']};
    }}
    QCheckBox {{
        font-size: 12px;
        color: {p['ink_soft']};
    }}
    """
