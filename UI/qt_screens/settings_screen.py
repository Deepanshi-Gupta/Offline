"""Native PySide6 port of settings_compliance_app.py (§14 of the UI audit).

Reuses SmartInternetAccessPanel as-is (already built and tested in
smart_internet_access_qt.py) for the Smart Internet Access section, and
converts the remaining Streamlit sections — religious compliance, image
compliance sensitivity, model/path configuration, language/RTL — into
native widgets.

As more sections were added (auto-update, storage), the screen moved to a
sub-navigation model (task N4): a QTabWidget with one tab per concern
(Connection / Compliance / Models & Paths / Language / Updates / Storage).
Besides organising the growing screen, splitting the dense rows across tabs
keeps any single view within the window width budget (see the width-debt
note in hasaballa_desktop_app.py) instead of one very wide stacked column.

Bilingual: every string is looked up through common.i18n.t() and re-set on
a language flip via retranslate(). The screen's own language selector is
wired to the same lang_manager singleton the header toggle uses, so the
two stay in sync in both directions.
"""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, show_toast
from smart_internet_access_qt import SmartInternetAccessPanel

# stable id, i18n name key, path, found, required — display name resolved via t().
# `required` models drive the first-launch gate (see hasaballa_desktop_app.py):
# if any required model is not found, the gate blocks the main UI until the
# paths are set or setup is explicitly skipped.
MODELS = [
    {"key": "sdxl", "name_key": "settings.model.sdxl", "path": "D:/Models/sdxl-flux", "found": True, "required": True},
    {"key": "wan", "name_key": "settings.model.wan", "path": "D:/Models/wan2.2", "found": True, "required": True},
    {"key": "latentsync", "name_key": "settings.model.latentsync", "path": "D:/Models/latentsync", "found": True, "required": True},
    {"key": "tts", "name_key": "settings.model.tts", "path": "D:/Models/tts-voices", "found": True, "required": True},
    {"key": "whisper", "name_key": "settings.model.whisper", "path": "D:/Models/whisper-large-v3", "found": True, "required": True},
    {"key": "nllb", "name_key": "settings.model.nllb", "path": "", "found": False, "required": True},
]

# stable id -> i18n key; medium is the default selection
SENSITIVITY_LEVELS = [
    ("low", "settings.sensitivity.low"),
    ("medium", "settings.sensitivity.medium"),
    ("high", "settings.sensitivity.high"),
]

# language combo order — index maps to lang code
LANG_ORDER = ["ar", "en"]

APP_VERSION = "1.4.0"
NEXT_VERSION = "1.5.0"
UPDATE_TICK_MS = 120

# Simulated on-disk usage by category (GB) and the volume's capacity.
STORAGE_GB = {"models": 42.0, "projects": 8.5, "cache": 3.2, "exports": 15.0}
DISK_TOTAL_GB = 120.0
STORAGE_CATS = [
    ("models", "settings.storage.cat.models"),
    ("projects", "settings.storage.cat.projects"),
    ("cache", "settings.storage.cat.cache"),
    ("exports", "settings.storage.cat.exports"),
]


class SettingsScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        self._model_badges = {}
        self._model_name_labels = {}
        self._model_path_edits = {}
        self._model_guidance = {}
        self._model_recheck = {}
        self._sensitivity_buttons = {}

        # auto-update state
        self.update_phase = "idle"  # idle | checking | available | installing | installed
        self._update_progress = 0.0
        self._update_timer = QTimer(self)
        self._update_timer.setInterval(UPDATE_TICK_MS)
        self._update_timer.timeout.connect(self._on_update_tick)

        # storage state (mutable copy so "clear cache" can zero a category)
        self.storage = dict(STORAGE_GB)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        # each tab is its own scroll area so a dense tab scrolls vertically
        # without stretching the others.
        self.tabs.addTab(self._scroll(self._build_connection_tab()), "")
        self.tabs.addTab(self._scroll(self._build_compliance_tab()), "")
        self.tabs.addTab(self._scroll(self._build_models_tab()), "")
        self.tabs.addTab(self._scroll(self._build_language_tab()), "")
        self.tabs.addTab(self._scroll(self._build_updates_tab()), "")
        self.tabs.addTab(self._scroll(self._build_storage_tab()), "")

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    @staticmethod
    def _scroll(inner: QWidget) -> QScrollArea:
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setWidget(inner)
        return sa

    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(2, 4, 6, 4)
        lay.setSpacing(16)
        return page, lay

    # ------------------------------------------------------------------
    # Tab: Connection
    # ------------------------------------------------------------------
    def _build_connection_tab(self) -> QWidget:
        page, lay = self._page()
        self.internet_panel = SmartInternetAccessPanel()
        wrap = QHBoxLayout()
        wrap.addWidget(self.internet_panel)
        wrap.addStretch(1)
        lay.addLayout(wrap)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Tab: Compliance
    # ------------------------------------------------------------------
    def _build_compliance_tab(self) -> QWidget:
        page, lay = self._page()

        rel_card = Card()
        rel_lay = rel_card.layout()
        self.religious_title = SectionLabel()
        rel_lay.addWidget(self.religious_title)
        self.religious_check = QCheckBox()
        self.religious_check.setChecked(True)
        rel_lay.addWidget(self.religious_check)
        self.religious_caption = CaptionLabel()
        rel_lay.addWidget(self.religious_caption)
        lay.addWidget(rel_card)

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
        lay.addWidget(img_card)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Tab: Models & Paths
    # ------------------------------------------------------------------
    def _build_models_tab(self) -> QWidget:
        page, lay = self._page()
        model_card = Card()
        model_lay = model_card.layout()
        self.models_title = SectionLabel()
        model_lay.addWidget(self.models_title)
        for model in MODELS:
            model_lay.addWidget(self._build_model_row(model))
        lay.addWidget(model_card)
        lay.addStretch(1)
        return page

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
        path_edit.textChanged.connect(lambda text, m=model: m.__setitem__("path", text))
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
    # Tab: Language
    # ------------------------------------------------------------------
    def _build_language_tab(self) -> QWidget:
        page, lay = self._page()
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
        lay.addWidget(lang_card)
        lay.addStretch(1)
        return page

    # ------------------------------------------------------------------
    # Tab: Updates (Task 14 / N1)
    # ------------------------------------------------------------------
    def _build_updates_tab(self) -> QWidget:
        page, lay = self._page()
        card = Card()
        cl = card.layout()
        self.updates_title = SectionLabel()
        cl.addWidget(self.updates_title)
        self.auto_update_check = QCheckBox()
        self.auto_update_check.setChecked(True)
        cl.addWidget(self.auto_update_check)
        self.auto_update_caption = CaptionLabel()
        cl.addWidget(self.auto_update_caption)

        chan_row = QHBoxLayout()
        self.update_channel_label = QLabel()
        chan_row.addWidget(self.update_channel_label)
        self.update_channel_combo = QComboBox()
        chan_row.addWidget(self.update_channel_combo)
        chan_row.addStretch(1)
        cl.addLayout(chan_row)

        self.update_version_label = QLabel()
        cl.addWidget(self.update_version_label)

        self.check_update_btn = QPushButton()
        self.check_update_btn.setProperty("variant", "primary")
        self.check_update_btn.clicked.connect(self._check_updates)
        cl.addWidget(self.check_update_btn)

        self.update_status = CaptionLabel()
        cl.addWidget(self.update_status)
        self.update_bar = QProgressBar()
        self.update_bar.setRange(0, 100)
        self.update_bar.setVisible(False)
        cl.addWidget(self.update_bar)
        self.install_update_btn = QPushButton()
        self.install_update_btn.setProperty("variant", "primary")
        self.install_update_btn.clicked.connect(self._install_update)
        self.install_update_btn.setVisible(False)
        cl.addWidget(self.install_update_btn)

        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _check_updates(self):
        self.update_phase = "checking"
        self._render_updates()
        self._update_timer.start()

    def _install_update(self):
        self.update_phase = "installing"
        self._update_progress = 0.0
        self.update_bar.setValue(0)
        self._render_updates()
        self._update_timer.start()

    def _on_update_tick(self):
        if self.update_phase == "checking":
            self._update_progress += 0.2
            if self._update_progress >= 1.0:
                self._update_timer.stop()
                self._update_progress = 0.0
                self.update_phase = "available"  # simulated: an update is waiting
                self._render_updates()
        elif self.update_phase == "installing":
            self._update_progress = min(1.0, self._update_progress + 0.1)
            self.update_bar.setValue(int(self._update_progress * 100))
            if self._update_progress >= 1.0:
                self._update_timer.stop()
                self.update_phase = "installed"
                self._render_updates()

    def _render_updates(self):
        self.update_version_label.setText(t("settings.updates.current", v=APP_VERSION))
        checking = self.update_phase == "checking"
        installing = self.update_phase == "installing"
        self.check_update_btn.setEnabled(not checking and not installing)
        self.check_update_btn.setText(t("settings.updates.checking") if checking else t("settings.updates.check_now"))
        self.update_bar.setVisible(installing)
        self.install_update_btn.setVisible(self.update_phase == "available")
        self.install_update_btn.setText(t("settings.updates.installing") if installing else t("settings.updates.install"))
        self.install_update_btn.setEnabled(not installing)

        if self.update_phase == "idle":
            self.update_status.setText("")
        elif checking:
            self.update_status.setText(t("settings.updates.checking"))
        elif self.update_phase == "available":
            self.update_status.setText(t("settings.updates.available", v=NEXT_VERSION))
        elif installing:
            self.update_status.setText(t("settings.updates.installing"))
        elif self.update_phase == "installed":
            self.update_status.setText(t("settings.updates.installed", v=NEXT_VERSION))

    # ------------------------------------------------------------------
    # Tab: Storage (N2)
    # ------------------------------------------------------------------
    def _build_storage_tab(self) -> QWidget:
        page, lay = self._page()
        card = Card()
        cl = card.layout()
        self.storage_title = SectionLabel()
        cl.addWidget(self.storage_title)
        self.storage_desc = CaptionLabel()
        cl.addWidget(self.storage_desc)
        self.storage_total = QLabel()
        self.storage_total.setStyleSheet("font-weight:700;")
        cl.addWidget(self.storage_total)

        self._storage_rows = {}
        for cat_key, _label_key in STORAGE_CATS:
            row = QHBoxLayout()
            name = QLabel()
            name.setFixedWidth(120)
            row.addWidget(name)
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            row.addWidget(bar, 1)
            size = CaptionLabel()
            size.setFixedWidth(90)
            row.addWidget(size)
            cl.addLayout(row)
            self._storage_rows[cat_key] = (name, bar, size)

        btn_row = QHBoxLayout()
        self.clear_cache_btn = QPushButton()
        self.clear_cache_btn.setProperty("variant", "danger")
        self.clear_cache_btn.clicked.connect(self._clear_cache)
        btn_row.addWidget(self.clear_cache_btn)
        self.open_storage_btn = QPushButton()
        self.open_storage_btn.clicked.connect(
            lambda: show_toast(self, t("settings.storage.opened_toast"), dark=self._dark)
        )
        btn_row.addWidget(self.open_storage_btn)
        btn_row.addStretch(1)
        cl.addLayout(btn_row)

        lay.addWidget(card)
        lay.addStretch(1)
        return page

    def _clear_cache(self):
        cleared = self.storage["cache"]
        if cleared <= 0:
            show_toast(self, t("settings.storage.cache_empty"), dark=self._dark)
            return
        self.storage["cache"] = 0.0
        show_toast(self, t("settings.storage.cache_cleared_toast", n=f"{cleared:g}"), dark=self._dark)
        self._render_storage()

    def _render_storage(self):
        used = sum(self.storage.values())
        self.storage_total.setText(t("settings.storage.total", used=f"{used:g}", total=f"{DISK_TOTAL_GB:g}"))
        for cat_key, label_key in STORAGE_CATS:
            name, bar, size = self._storage_rows[cat_key]
            name.setText(t(label_key))
            gb = self.storage[cat_key]
            bar.setValue(int(gb / DISK_TOTAL_GB * 100))
            size.setText(t("settings.storage.size_gb", n=f"{gb:g}"))
        self.clear_cache_btn.setEnabled(self.storage["cache"] > 0)

    # ------------------------------------------------------------------
    # i18n
    # ------------------------------------------------------------------
    def retranslate(self):
        self.tabs.setTabText(0, t("settings.tab.connection"))
        self.tabs.setTabText(1, t("settings.tab.compliance"))
        self.tabs.setTabText(2, t("settings.tab.models"))
        self.tabs.setTabText(3, t("settings.tab.language"))
        self.tabs.setTabText(4, t("settings.tab.updates"))
        self.tabs.setTabText(5, t("settings.tab.storage"))

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

        self.updates_title.setText(t("settings.updates.title"))
        self.auto_update_check.setText(t("settings.updates.auto_check"))
        self.auto_update_caption.setText(t("settings.updates.auto_caption"))
        self.update_channel_label.setText(t("settings.updates.channel"))
        chan_idx = max(0, self.update_channel_combo.currentIndex())
        self.update_channel_combo.blockSignals(True)
        self.update_channel_combo.clear()
        self.update_channel_combo.addItems([t("settings.updates.channel.stable"), t("settings.updates.channel.beta")])
        self.update_channel_combo.setCurrentIndex(chan_idx)
        self.update_channel_combo.blockSignals(False)
        self._render_updates()

        self.storage_title.setText(t("settings.storage.title"))
        self.storage_desc.setText(t("settings.storage.desc"))
        self.clear_cache_btn.setText(t("settings.storage.clear_cache"))
        self.open_storage_btn.setText(t("settings.storage.open_folder"))
        self._render_storage()

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
