"""Native PySide6 port of character_pack_manager_app.py (§4 of the UI
audit): character list + editor, up to 8 reference-image slots per
character, with PER-IMAGE controls — weighting (0–100%), a linked voice,
and an age/angle label — plus real SHA-256 identity-conflict detection
(byte-identical slot pairs) and JSON import/export via native dialogs.

Cap (resolved with the client): 8 reference images per character is the
target/maximum; fewer is allowed and handled gracefully — a character with
1–7 images is "incomplete" but fully usable, not blocked.
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

SLOTS_PER_CHARACTER = 8  # cap/target per character; fewer is allowed
FACE_PATHS = face_paths()
VOICE_NAMES = [f"{v['icon']} {v['name']}" for v in VOICES]

# per-image metadata option lists — (stable id, i18n key). ids are stored so
# the choice survives a language flip and JSON round-trip.
AGE_OPTIONS = [("child", "cp.age.child"), ("teen", "cp.age.teen"), ("adult", "cp.age.adult"), ("senior", "cp.age.senior")]
ANGLE_OPTIONS = [
    ("front", "cp.angle.front"),
    ("three_quarter", "cp.angle.three_quarter"),
    ("profile", "cp.angle.profile"),
    ("low", "cp.angle.low"),
    ("high", "cp.angle.high"),
]
AGE_IDS = [o[0] for o in AGE_OPTIONS]
ANGLE_IDS = [o[0] for o in ANGLE_OPTIONS]
DEFAULT_AGE = "adult"
DEFAULT_ANGLE = "front"


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


def _new_character(name, filled=0, dup_slots=None):
    images = [None] * SLOTS_PER_CHARACTER
    weights = [1.0] * SLOTS_PER_CHARACTER
    slot_voices = [0] * SLOTS_PER_CHARACTER
    ages = [DEFAULT_AGE] * SLOTS_PER_CHARACTER
    angles = [DEFAULT_ANGLE] * SLOTS_PER_CHARACTER
    for i in range(filled):
        images[i] = _demo_image_bytes(i)
    if dup_slots:
        a, b = dup_slots
        images[b] = images[a]
    return {"name": name, "images": images, "weights": weights, "slot_voices": slot_voices, "ages": ages, "angles": angles}


def _clamp_index(value, length, default=0):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if 0 <= value < length else default


STATUS_TONE = {"empty": "neutral", "incomplete": "warning", "complete": "success", "conflict": "danger"}
STATUS_KEY = {"empty": "cp.status.empty", "incomplete": "cp.status.incomplete", "complete": "cp.status.complete", "conflict": "cp.status.conflict"}


class CharacterPackScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self.characters = self._seed_characters()
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

    @staticmethod
    def _seed_characters():
        layla = _new_character("Layla", filled=8, dup_slots=(0, 4))
        # showcase per-image variety (voice / angle differ per slot)
        demo_voices = [3, 3, 1, 1, 3, 0, 5, 2]
        for i in range(SLOTS_PER_CHARACTER):
            layla["slot_voices"][i] = demo_voices[i] % len(VOICES)
            layla["angles"][i] = ANGLE_IDS[i % len(ANGLE_IDS)]
            layla["weights"][i] = round(0.5 + 0.06 * i, 2)
        omar = _new_character("Omar", filled=3)
        for i in range(3):
            omar["angles"][i] = ANGLE_IDS[i % len(ANGLE_IDS)]
        return [layla, omar]

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _linked_voice_names(self, char) -> list:
        idxs = sorted({char["slot_voices"][i] for i, im in enumerate(char["images"]) if im is not None})
        return [VOICE_NAMES[_clamp_index(i, len(VOICES))] for i in idxs]

    def _compact_combo(self, items, current_index, on_index_changed) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentIndex(current_index)
        # shrink to the column instead of demanding the longest item's width
        combo.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        combo.setMinimumContentsLength(6)
        combo.currentIndexChanged.connect(on_index_changed)
        return combo

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

        # per-image voice linking → summarize the distinct voices in this pack
        names = self._linked_voice_names(char)
        voices_caption = CaptionLabel(t("cp.voices_linked", voices="، ".join(names)) if names else t("cp.voices_none"))
        lay.addWidget(voices_caption)

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

    # ------------------------------------------------------------------
    # import / export
    # ------------------------------------------------------------------
    def _coerce_character(self, c: dict) -> dict:
        n = SLOTS_PER_CHARACTER

        def pad(seq, fill):
            seq = list(seq) if seq is not None else []
            return (seq + [fill] * n)[:n]

        images = pad([base64.b64decode(im) if im else None for im in c.get("images", [])], None)
        weights = [min(1.0, max(0.0, float(w) if _is_number(w) else 1.0)) for w in pad(c.get("weights"), 1.0)]
        # backward-compat: a legacy flat voice_idx becomes every slot's voice
        legacy = c.get("voice_idx")
        raw_voices = c.get("slot_voices")
        if raw_voices is None and legacy is not None:
            raw_voices = [legacy] * n
        slot_voices = [_clamp_index(v, len(VOICES)) for v in pad(raw_voices, 0)]
        ages = [a if a in AGE_IDS else DEFAULT_AGE for a in pad(c.get("ages"), DEFAULT_AGE)]
        angles = [a if a in ANGLE_IDS else DEFAULT_ANGLE for a in pad(c.get("angles"), DEFAULT_ANGLE)]
        return {"name": str(c.get("name", "")), "images": images, "weights": weights,
                "slot_voices": slot_voices, "ages": ages, "angles": angles}

    def _import_json(self):
        path, _f = QFileDialog.getOpenFileName(self, t("cp.btn.import"), "", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.characters = [self._coerce_character(c) for c in data]
            self.editing_idx = None
            self.stack.setCurrentWidget(self.list_page)
            self._render_list()
            show_toast(self, t("cp.import.success", n=len(self.characters)), dark=self._dark)
        except Exception as e:  # noqa: BLE001 — surfaced to the user as a toast
            show_toast(self, t("cp.import.failed", err=str(e)), dark=self._dark)

    def _export_json(self):
        path, _f = QFileDialog.getSaveFileName(self, t("cp.btn.export"), "character_pack.json", "JSON (*.json)")
        if not path:
            return
        payload = json.dumps(
            [
                {
                    "name": c["name"],
                    "weights": c["weights"],
                    "slot_voices": c["slot_voices"],
                    "ages": c["ages"],
                    "angles": c["angles"],
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

        name_col = QVBoxLayout()
        self.name_label = QLabel()
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)
        name_col.addWidget(self.name_label)
        name_col.addWidget(self.name_edit)
        lay.addLayout(name_col)

        status_row = QHBoxLayout()
        self.editor_badge = StatusBadge()
        status_row.addWidget(self.editor_badge)
        self.editor_count_label = QLabel()
        status_row.addWidget(self.editor_count_label)
        status_row.addStretch(1)
        lay.addLayout(status_row)

        self.under_target_label = QLabel()
        self.under_target_label.setWordWrap(True)
        lay.addWidget(self.under_target_label)

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

    def _render_editor(self):
        if self.editing_idx is None:
            return
        char = self.characters[self.editing_idx]
        s = semantic(self._dark)

        self.name_edit.blockSignals(True)
        self.name_edit.setText(char["name"])
        self.name_edit.blockSignals(False)

        status, filled = character_status(char)
        self.editor_badge.setText(t(STATUS_KEY[status]))
        self.editor_badge.set_tone(STATUS_TONE[status], self._dark)
        self.editor_count_label.setText(t("cp.images_count_full", filled=filled, total=SLOTS_PER_CHARACTER))

        # "fewer is allowed" note — usable but below the 8-image target
        under_target = 0 < filled < SLOTS_PER_CHARACTER and status != "conflict"
        self.under_target_label.setVisible(under_target)
        if under_target:
            self.under_target_label.setText(t("cp.under_target", filled=filled))
            self.under_target_label.setStyleSheet(f"color:{s['warning_fg_strong']}; font-size:11.5px;")

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

            # weighting 0–100%
            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 100)
            slider.setValue(int(round(char["weights"][slot] * 100)))
            slider.valueChanged.connect(lambda v, sl=slot: self._on_weight_changed(sl, v))
            lay.addWidget(slider)
            caption = CaptionLabel(t("cp.slot.caption", n=slot + 1, w=int(round(char["weights"][slot] * 100))))
            lay.addWidget(caption)
            self._slot_captions[slot] = caption

            # per-image linked voice
            lay.addWidget(CaptionLabel(t("cp.slot.voice")))
            voice_combo = self._compact_combo(
                VOICE_NAMES, _clamp_index(char["slot_voices"][slot], len(VOICES)),
                lambda idx, sl=slot: self._set_slot_field(sl, "slot_voices", idx),
            )
            lay.addWidget(voice_combo)

            # per-image age + angle labels
            meta_row = QHBoxLayout()
            age_col = QVBoxLayout()
            age_col.setSpacing(2)
            age_col.addWidget(CaptionLabel(t("cp.slot.age")))
            age_combo = self._compact_combo(
                [t(k) for _i, k in AGE_OPTIONS], AGE_IDS.index(char["ages"][slot] if char["ages"][slot] in AGE_IDS else DEFAULT_AGE),
                lambda idx, sl=slot: self._set_slot_field(sl, "ages", AGE_IDS[idx]),
            )
            age_col.addWidget(age_combo)
            meta_row.addLayout(age_col)

            angle_col = QVBoxLayout()
            angle_col.setSpacing(2)
            angle_col.addWidget(CaptionLabel(t("cp.slot.angle")))
            angle_combo = self._compact_combo(
                [t(k) for _i, k in ANGLE_OPTIONS], ANGLE_IDS.index(char["angles"][slot] if char["angles"][slot] in ANGLE_IDS else DEFAULT_ANGLE),
                lambda idx, sl=slot: self._set_slot_field(sl, "angles", ANGLE_IDS[idx]),
            )
            angle_col.addWidget(angle_combo)
            meta_row.addLayout(angle_col)
            lay.addLayout(meta_row)

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

    def _set_slot_field(self, slot: int, field: str, value):
        if self.editing_idx is not None:
            self.characters[self.editing_idx][field][slot] = value

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
        self.characters[self.editing_idx]["weights"][slot] = value / 100.0
        # update just this slot's caption in place — a full _render_editor()
        # here would rebuild the grid mid-drag and destroy the QSlider being dragged
        caption = self._slot_captions.get(slot)
        if caption is not None:
            caption.setText(t("cp.slot.caption", n=slot + 1, w=value))

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("cp.subtitle"))
        self.add_btn.setText(t("cp.btn.add"))
        self.import_btn.setText(t("cp.btn.import"))
        self.export_btn.setText(t("cp.btn.export"))
        self.empty_label.setText(t("cp.empty"))
        self.back_btn.setText(t("cp.btn.back"))
        self.name_label.setText(t("cp.name.label"))
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


def _is_number(v) -> bool:
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False
