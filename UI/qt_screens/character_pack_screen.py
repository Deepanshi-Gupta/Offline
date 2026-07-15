"""Native PySide6 port of character_pack_manager_app.py (§4 of the UI
audit): character list + editor, 8 reference-image slots per character
with per-image weighting, a paired voice, real SHA-256 identity-conflict
detection (byte-identical slot pairs), and JSON import/export via native
file dialogs.
"""

import base64
import hashlib
import json

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout, show_toast
from common.style import face_paths
from common.voices import VOICES

SLOTS_PER_CHARACTER = 8
FACE_PATHS = face_paths()
VOICE_NAMES = [f"{v['icon']} {v['name']}" for v in VOICES]


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


STATUS_TONE = {"empty": "neutral", "incomplete": "warning", "complete": "success", "conflict": "danger"}
STATUS_KEY = {"empty": "cp.status.empty", "incomplete": "cp.status.incomplete", "complete": "cp.status.complete", "conflict": "cp.status.conflict"}


class CharacterPackScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self.characters = [
            _new_character("Layla", filled=8, dup_slots=(0, 4), voice_idx=3),
            _new_character("Omar", filled=3, voice_idx=0),
        ]
        self.editing_idx = None
        self._slot_captions = {}

        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 4, 4)

        self.subtitle = CaptionLabel()
        outer.addWidget(self.subtitle)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.list_page = self._build_list_page()
        self.editor_page = self._build_editor_page()
        self.stack.addWidget(self.list_page)
        self.stack.addWidget(self.editor_page)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()
        self._render_list()

    # ------------------------------------------------------------------
    # list page
    # ------------------------------------------------------------------
    def _build_list_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)

        toolbar = QHBoxLayout()
        self.add_btn = QPushButton()
        self.add_btn.setProperty("variant", "primary")
        self.add_btn.clicked.connect(self._add_character)
        self.import_btn = QPushButton()
        self.import_btn.clicked.connect(self._import_json)
        self.export_btn = QPushButton()
        self.export_btn.clicked.connect(self._export_json)
        toolbar.addWidget(self.add_btn)
        toolbar.addWidget(self.import_btn)
        toolbar.addWidget(self.export_btn)
        lay.addLayout(toolbar)

        self.empty_label = QLabel()
        self.empty_label.setWordWrap(True)
        lay.addWidget(self.empty_label)

        self.cards_grid = QGridLayout()
        self.cards_grid.setSpacing(12)
        lay.addLayout(self.cards_grid)
        lay.addStretch(1)
        return page

    def _render_list(self):
        clear_layout(self.cards_grid)
        self.empty_label.setVisible(not self.characters)
        if not self.characters:
            return
        s = semantic(self._dark)
        for i, char in enumerate(self.characters):
            card = self._build_character_card(i, char, s)
            row, col = divmod(i, 3)
            self.cards_grid.addWidget(card, row, col)

    def _build_character_card(self, i: int, char: dict, s: dict) -> QWidget:
        card = Card()
        lay = card.layout()

        thumb_data = next((im for im in char["images"] if im), None)
        thumb = QLabel()
        thumb.setFixedSize(QSize(200, 130))
        thumb.setAlignment(Qt.AlignCenter)
        if thumb_data:
            pix = QPixmap()
            pix.loadFromData(QByteArray(thumb_data))
            thumb.setPixmap(pix.scaled(thumb.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            thumb.setScaledContents(True)
        else:
            thumb.setText("")
            thumb.setStyleSheet(f"background:{s['surface_muted']}; border-radius:10px; font-size:34px; color:{s['ink_fainter']};")
        lay.addWidget(thumb)

        name_label = QLabel(f"{char['name']}")
        name_label.setStyleSheet("font-weight:700;")
        lay.addWidget(name_label)

        status, filled = character_status(char)
        status_row = QHBoxLayout()
        badge = StatusBadge(t(STATUS_KEY[status]), tone=STATUS_TONE[status], dark=self._dark)
        status_row.addWidget(badge)
        status_row.addWidget(QLabel(t("cp.images_count", filled=filled, total=SLOTS_PER_CHARACTER)))
        status_row.addStretch(1)
        lay.addLayout(status_row)

        if status == "conflict":
            a, b = find_conflict_pairs(char["images"])[0]
            warn = QLabel(t("cp.conflict_warning", a=a + 1, b=b + 1))
            warn.setWordWrap(True)
            warn.setStyleSheet(f"color:{s['danger_fg_strong']}; font-size:11px;")
            lay.addWidget(warn)

        lay.addWidget(CaptionLabel(t("cp.voice_label", voice=VOICE_NAMES[char["voice_idx"]])))

        btn_row = QHBoxLayout()
        edit_btn = QPushButton(t("cp.btn.edit"))
        edit_btn.clicked.connect(lambda _c=False, idx=i: self._edit_character(idx))
        remove_btn = QPushButton(t("cp.btn.remove"))
        remove_btn.setProperty("variant", "danger")
        remove_btn.clicked.connect(lambda _c=False, idx=i: self._remove_character(idx))
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(remove_btn)
        lay.addLayout(btn_row)

        return card

    def _add_character(self):
        self.characters.append(_new_character(f"Character {len(self.characters) + 1}"))
        self._render_list()

    def _remove_character(self, idx: int):
        self.characters.pop(idx)
        self._render_list()

    def _import_json(self):
        path, _f = QFileDialog.getOpenFileName(self, t("cp.btn.import"), "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            chars = [
                {
                    "name": c["name"],
                    "voice_idx": c["voice_idx"],
                    "weights": c["weights"],
                    "images": [base64.b64decode(im) if im else None for im in c["images"]],
                }
                for c in data
            ]
            self.characters = chars
            self._render_list()
            show_toast(self, t("cp.import.success", n=len(chars)), dark=self._dark)
        except Exception as e:
            show_toast(self, t("cp.import.failed", err=str(e)), dark=self._dark)

    def _export_json(self):
        path, _f = QFileDialog.getSaveFileName(self, t("cp.btn.export"), "character_pack.json", "JSON (*.json)")
        if not path:
            return
        payload = json.dumps(
            [
                {
                    "name": c["name"],
                    "voice_idx": c["voice_idx"],
                    "weights": c["weights"],
                    "images": [base64.b64encode(im).decode() if im else None for im in c["images"]],
                }
                for c in self.characters
            ]
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)

    # ------------------------------------------------------------------
    # editor page
    # ------------------------------------------------------------------
    def _build_editor_page(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 8, 0, 0)

        self.back_btn = QPushButton()
        self.back_btn.clicked.connect(self._back_to_list)
        lay.addWidget(self.back_btn)

        form_row = QHBoxLayout()
        name_col = QVBoxLayout()
        self.name_label = QLabel()
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)
        name_col.addWidget(self.name_label)
        name_col.addWidget(self.name_edit)
        form_row.addLayout(name_col, 2)

        voice_col = QVBoxLayout()
        self.voice_label = QLabel()
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(VOICE_NAMES)
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        voice_col.addWidget(self.voice_label)
        voice_col.addWidget(self.voice_combo)
        form_row.addLayout(voice_col, 1)
        lay.addLayout(form_row)

        status_row = QHBoxLayout()
        self.editor_badge = StatusBadge()
        status_row.addWidget(self.editor_badge)
        self.editor_count_label = QLabel()
        status_row.addWidget(self.editor_count_label)
        status_row.addStretch(1)
        lay.addLayout(status_row)

        self.conflict_warnings = QVBoxLayout()
        lay.addLayout(self.conflict_warnings)

        self.slots_title = SectionLabel()
        lay.addWidget(self.slots_title)

        self.slots_grid = QGridLayout()
        self.slots_grid.setSpacing(10)
        lay.addLayout(self.slots_grid)
        lay.addStretch(1)
        return page

    def _edit_character(self, idx: int):
        self.editing_idx = idx
        self.stack.setCurrentWidget(self.editor_page)
        self._render_editor()

    def _back_to_list(self):
        self.editing_idx = None
        self.stack.setCurrentWidget(self.list_page)
        self._render_list()

    def _on_name_changed(self):
        if self.editing_idx is not None:
            self.characters[self.editing_idx]["name"] = self.name_edit.text()

    def _on_voice_changed(self, index: int):
        if self.editing_idx is not None:
            self.characters[self.editing_idx]["voice_idx"] = index

    def _render_editor(self):
        if self.editing_idx is None:
            return
        char = self.characters[self.editing_idx]
        s = semantic(self._dark)

        self.name_edit.blockSignals(True)
        self.name_edit.setText(char["name"])
        self.name_edit.blockSignals(False)
        self.voice_combo.blockSignals(True)
        self.voice_combo.setCurrentIndex(char["voice_idx"])
        self.voice_combo.blockSignals(False)

        status, filled = character_status(char)
        self.editor_badge.setText(t(STATUS_KEY[status]))
        self.editor_badge.set_tone(STATUS_TONE[status], self._dark)
        self.editor_count_label.setText(t("cp.images_count_full", filled=filled, total=SLOTS_PER_CHARACTER))

        clear_layout(self.conflict_warnings)
        if status == "conflict":
            for a, b in find_conflict_pairs(char["images"]):
                warn = QLabel(t("cp.conflict_warning", a=a + 1, b=b + 1))
                warn.setStyleSheet(f"color:{s['danger_fg_strong']}; font-weight:600;")
                self.conflict_warnings.addWidget(warn)

        clear_layout(self.slots_grid)
        self._slot_captions = {}
        for slot in range(SLOTS_PER_CHARACTER):
            widget = self._build_slot(slot, char, s)
            row, col = divmod(slot, 4)
            self.slots_grid.addWidget(widget, row, col)

    def _build_slot(self, slot: int, char: dict, s: dict) -> QWidget:
        card = Card(flat=True, margins=(8, 8, 8, 8), spacing=4)
        lay = card.layout()
        image_bytes = char["images"][slot]

        if image_bytes is not None:
            img = QLabel()
            img.setFixedSize(QSize(140, 100))
            pix = QPixmap()
            pix.loadFromData(QByteArray(image_bytes))
            img.setPixmap(pix.scaled(img.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
            img.setScaledContents(True)
            lay.addWidget(img)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(char["weights"][slot] * 100))
            slider.valueChanged.connect(lambda v, sl=slot: self._on_weight_changed(sl, v))
            lay.addWidget(slider)

            caption = CaptionLabel(t("cp.slot.caption", n=slot + 1, w=f"{char['weights'][slot]:.2f}"))
            lay.addWidget(caption)
            self._slot_captions[slot] = caption

            remove_btn = QPushButton(t("cp.btn.remove"))
            remove_btn.clicked.connect(lambda _c=False, sl=slot: self._remove_slot_image(sl))
            lay.addWidget(remove_btn)
        else:
            placeholder = QLabel(t("cp.slot.empty", n=slot + 1))
            placeholder.setFixedSize(QSize(140, 100))
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setWordWrap(True)
            placeholder.setProperty("role", "emptySlot")
            placeholder.setStyleSheet(f"border:2px dashed {s['dashed_border']}; border-radius:10px; color:{s['ink_fainter']}; font-size:11px;")
            placeholder.setCursor(Qt.PointingHandCursor)
            lay.addWidget(placeholder)

            pick_btn = QPushButton("+")
            pick_btn.clicked.connect(lambda _c=False, sl=slot: self._pick_slot_image(sl))
            lay.addWidget(pick_btn)

        return card

    def _pick_slot_image(self, slot: int):
        path, _f = QFileDialog.getOpenFileName(self, t("cp.slot.empty", n=slot + 1), "", "Images (*.png *.jpg *.jpeg)")
        if not path:
            return
        with open(path, "rb") as f:
            data = f.read()
        self.characters[self.editing_idx]["images"][slot] = data
        self._render_editor()

    def _remove_slot_image(self, slot: int):
        self.characters[self.editing_idx]["images"][slot] = None
        self._render_editor()

    def _on_weight_changed(self, slot: int, value: int):
        weight = value / 100.0
        self.characters[self.editing_idx]["weights"][slot] = weight
        # update just this slot's caption in place — a full _render_editor()
        # here would rebuild the grid mid-drag and destroy the QSlider being dragged
        caption = self._slot_captions.get(slot)
        if caption is not None:
            caption.setText(t("cp.slot.caption", n=slot + 1, w=f"{weight:.2f}"))

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("cp.subtitle"))
        self.add_btn.setText(t("cp.btn.add"))
        self.import_btn.setText(t("cp.btn.import"))
        self.export_btn.setText(t("cp.btn.export"))
        self.empty_label.setText(t("cp.empty"))
        self.back_btn.setText(t("cp.btn.back"))
        self.name_label.setText(t("cp.name.label"))
        self.voice_label.setText(t("cp.voice.label"))
        self.slots_title.setText(t("cp.slots.title"))
        self._render_list()
        if self.editing_idx is not None:
            self._render_editor()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_list()
        if self.editing_idx is not None:
            self._render_editor()
