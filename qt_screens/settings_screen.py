"""Native PySide6 port of settings_compliance_app.py (§14 of the UI audit).

Reuses SmartInternetAccessPanel as-is (already built and tested in
smart_internet_access_qt.py) for the Smart Internet Access section, and
converts the remaining Streamlit sections — religious compliance, image
compliance sensitivity, model/path configuration, language/RTL — into
native widgets. Same content and behavior as the Streamlit source; only
the widget toolkit changed.

Bilingual: every string is looked up through common.i18n.t() and re-set on
a language flip via retranslate(). The screen's own language selector is
wired to the same lang_manager singleton the header toggle uses, so the
two stay in sync in both directions.
"""

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge
from smart_internet_access_qt import SmartInternetAccessPanel

# stable id, i18n name key, path, found — display name resolved via t()
MODELS = [
    {"key": "sdxl", "name_key": "settings.model.sdxl", "path": "D:/Models/sdxl-flux", "found": True},
    {"key": "wan", "name_key": "settings.model.wan", "path": "D:/Models/wan2.2", "found": True},
    {"key": "latentsync", "name_key": "settings.model.latentsync", "path": "D:/Models/latentsync", "found": True},
    {"key": "tts", "name_key": "settings.model.tts", "path": "D:/Models/tts-voices", "found": True},
    {"key": "whisper", "name_key": "settings.model.whisper", "path": "D:/Models/whisper-large-v3", "found": True},
    {"key": "nllb", "name_key": "settings.model.nllb", "path": "", "found": False},
]

# stable id -> i18n key; medium is the default selection
SENSITIVITY_LEVELS = [
    ("low", "settings.sensitivity.low"),
    ("medium", "settings.sensitivity.medium"),
    ("high", "settings.sensitivity.high"),
]

# language combo order — index maps to lang code
LANG_ORDER = ["ar", "en"]


class SettingsScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._dark = False
        self._model_badges = {}
        self._model_name_labels = {}
        self._model_path_edits = {}
        self._model_guidance = {}
        self._model_recheck = {}
        self._sensitivity_buttons = {}

        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(0, 0, 4, 4)
        outer.setSpacing(18)

        # ---- Smart Internet Access (already-built native widget) ----
        self.internet_panel = SmartInternetAccessPanel()
        wrap = QHBoxLayout()
        wrap.addWidget(self.internet_panel)
        wrap.addStretch(1)
        outer.addLayout(wrap)

        # ---- Religious compliance ----
        rel_card = Card()
        rel_lay = rel_card.layout()
        self.religious_title = SectionLabel()
        rel_lay.addWidget(self.religious_title)
        self.religious_check = QCheckBox()
        self.religious_check.setChecked(True)
        rel_lay.addWidget(self.religious_check)
        self.religious_caption = CaptionLabel()
        rel_lay.addWidget(self.religious_caption)
        outer.addWidget(rel_card)

        # ---- Image compliance / modesty filter ----
        img_card = Card()
        img_lay = img_card.layout()
        self.image_title = SectionLabel()
        img_lay.addWidget(self.image_title)
        self.image_compliance_check = QCheckBox()
        self.image_compliance_check.setChecked(True)
        img_lay.addWidget(self.image_compliance_check)

        sens_row = QHBoxLayout()
        self.sensitivity_label = QLabel()
        sens_row.addWidget(self.sensitivity_label)
        self.sensitivity_group = QButtonGroup(self)
        for level_id, _key in SENSITIVITY_LEVELS:
            btn = QRadioButton()
            if level_id == "medium":
                btn.setChecked(True)
            self.sensitivity_group.addButton(btn)
            self._sensitivity_buttons[level_id] = btn
            sens_row.addWidget(btn)
        sens_row.addStretch(1)
        img_lay.addLayout(sens_row)
        self.image_caption = CaptionLabel()
        img_lay.addWidget(self.image_caption)

        self.image_compliance_check.toggled.connect(
            lambda on: [b.setEnabled(on) for b in self._sensitivity_buttons.values()]
        )

        outer.addWidget(img_card)

        # ---- Model / path configuration ----
        model_card = Card()
        model_lay = model_card.layout()
        self.models_title = SectionLabel()
        model_lay.addWidget(self.models_title)
        for model in MODELS:
            model_lay.addWidget(self._build_model_row(model))
        outer.addWidget(model_card)

        # ---- Language / RTL ----
        lang_card = Card()
        lang_lay = lang_card.layout()
        self.lang_title = SectionLabel()
        lang_lay.addWidget(self.lang_title)
        self.language_combo = QComboBox()
        self.language_combo.addItems(["العربية", "English"])
        lang_lay.addWidget(self.language_combo)
        self.language_note = CaptionLabel()
        lang_lay.addWidget(self.language_note)
        self.language_combo.currentIndexChanged.connect(self._on_combo_changed)
        outer.addWidget(lang_card)

        outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    def _build_model_row(self, model: dict) -> QFrame:
        row = Card(flat=True, margins=(12, 10, 12, 10), spacing=6)
        lay = row.layout()

        head = QHBoxLayout()
        name_label = QLabel()
        badge = StatusBadge(tone="success" if model["found"] else "danger")
        head.addWidget(name_label, 1)
        head.addWidget(badge)
        lay.addLayout(head)

        path_edit = QLineEdit(model["path"])
        lay.addWidget(path_edit)

        guidance = CaptionLabel()
        recheck_btn = QPushButton()
        recheck_btn.setProperty("variant", "primary")
        guidance.setVisible(not model["found"])
        recheck_btn.setVisible(not model["found"])

        def do_recheck():
            model["found"] = True
            badge.setText(t("settings.models.found"))
            badge.set_tone("success", self._dark)
            guidance.setVisible(False)
            recheck_btn.setVisible(False)

        recheck_btn.clicked.connect(do_recheck)
        lay.addWidget(guidance)
        lay.addWidget(recheck_btn)

        self._model_badges[model["key"]] = badge
        self._model_name_labels[model["key"]] = name_label
        self._model_path_edits[model["key"]] = path_edit
        self._model_guidance[model["key"]] = guidance
        self._model_recheck[model["key"]] = recheck_btn
        return row

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def retranslate(self):
        self.religious_title.setText(t("settings.religious.title"))
        self.religious_check.setText(t("settings.religious.check"))
        self.religious_caption.setText(t("settings.religious.caption"))

        self.image_title.setText(t("settings.image.title"))
        self.image_compliance_check.setText(t("settings.image.check"))
        self.sensitivity_label.setText(t("settings.image.sensitivity"))
        for level_id, key in SENSITIVITY_LEVELS:
            self._sensitivity_buttons[level_id].setText(t(key))
        self.image_caption.setText(t("settings.image.caption"))

        self.models_title.setText(t("settings.models.title"))
        for model in MODELS:
            key = model["key"]
            name = t(model["name_key"])
            self._model_name_labels[key].setText(name)
            badge = self._model_badges[key]
            badge.setText(t("settings.models.found") if model["found"] else t("settings.models.missing"))
            self._model_path_edits[key].setPlaceholderText(t("settings.models.path_placeholder"))
            self._model_guidance[key].setText(t("settings.model.missing_guidance", name=name))
            self._model_recheck[key].setText(t("settings.models.recheck"))

        self.lang_title.setText(t("settings.lang.title"))
        self._sync_combo_to_lang()
        self._update_language_note()

    def _update_language_note(self):
        self.language_note.setText(
            t("settings.lang.note_ar") if lang_manager.is_rtl() else t("settings.lang.note_en")
        )

    def _sync_combo_to_lang(self):
        idx = LANG_ORDER.index(lang_manager.lang)
        if self.language_combo.currentIndex() != idx:
            self.language_combo.blockSignals(True)
            self.language_combo.setCurrentIndex(idx)
            self.language_combo.blockSignals(False)

    def _on_combo_changed(self, index: int):
        lang_manager.set_lang(LANG_ORDER[index])  # drives the whole app; retranslate() follows via the signal

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    # ------------------------------------------------------------------
    # theming
    # ------------------------------------------------------------------
    def set_dark(self, dark: bool):
        self._dark = dark
        self.internet_panel.set_dark(dark)
        for key, badge in self._model_badges.items():
            model = next(m for m in MODELS if m["key"] == key)
            badge.set_tone("success" if model["found"] else "danger", dark)
