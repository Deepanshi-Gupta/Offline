"""Native PySide6 port of settings_compliance_app.py (§14 of the UI audit).

Reuses SmartInternetAccessPanel as-is (already built and tested in
smart_internet_access_qt.py) for the Smart Internet Access section, and
converts the remaining Streamlit sections — religious compliance, image
compliance sensitivity, model/path configuration, language/RTL — into
native widgets. Same content and behavior as the Streamlit source; only
the widget toolkit changed.
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

from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge
from smart_internet_access_qt import SmartInternetAccessPanel

MODELS = [
    {"key": "sdxl", "name": "SDXL / FLUX (توليد الصور)", "path": "D:/Models/sdxl-flux", "found": True},
    {"key": "wan", "name": "WAN 2.2 (توليد الحركة)", "path": "D:/Models/wan2.2", "found": True},
    {"key": "latentsync", "name": "LatentSync (مزامنة الشفاه)", "path": "D:/Models/latentsync", "found": True},
    {"key": "tts", "name": "مكتبة الأصوات (TTS)", "path": "D:/Models/tts-voices", "found": True},
    {"key": "whisper", "name": "Whisper (تحويل الصوت إلى نص)", "path": "D:/Models/whisper-large-v3", "found": True},
    {"key": "nllb", "name": "NLLB-200 (الترجمة)", "path": "", "found": False},
]

SENSITIVITY_LEVELS = ["منخفضة", "متوسطة", "عالية"]


class SettingsScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._dark = False
        self._model_rows = {}

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
        rel_lay.addWidget(SectionLabel("🛡️ الامتثال الديني"))
        self.religious_check = QCheckBox(
            "حظر تلقائي للصوت غير الملائم دينياً (الموسيقى/العود/الطرب أثناء الأذان أو تلاوة القرآن أو الدعاء)"
        )
        self.religious_check.setChecked(True)
        self.religious_check.setWordWrap(True)
        rel_lay.addWidget(self.religious_check)
        rel_lay.addWidget(
            CaptionLabel("مُفعّل تلقائياً في شاشة طبقات الصوت (§7) عند تحديد أن المشهد يحتوي على صوت ديني.")
        )
        outer.addWidget(rel_card)

        # ---- Image compliance / modesty filter ----
        img_card = Card()
        img_lay = img_card.layout()
        img_lay.addWidget(SectionLabel("🖼️ فلتر الحشمة في الصور"))
        self.image_compliance_check = QCheckBox("رفض تلقائي وإعادة توليد الصور غير الملائمة")
        self.image_compliance_check.setChecked(True)
        img_lay.addWidget(self.image_compliance_check)

        sens_row = QHBoxLayout()
        sens_label = QLabel("درجة الحساسية:")
        sens_row.addWidget(sens_label)
        self.sensitivity_group = QButtonGroup(self)
        self.sensitivity_buttons = {}
        for level in SENSITIVITY_LEVELS:
            btn = QRadioButton(level)
            if level == "متوسطة":
                btn.setChecked(True)
            self.sensitivity_group.addButton(btn)
            self.sensitivity_buttons[level] = btn
            sens_row.addWidget(btn)
        sens_row.addStretch(1)
        img_lay.addLayout(sens_row)
        img_lay.addWidget(
            CaptionLabel(
                "درجة حساسية أعلى ترفض تلقائياً المزيد من الصور الحدّية (§3). يُطبَّق بصمت — لا تُعرض الصورة "
                "المرفوضة أبداً للمستخدم."
            )
        )
        outer.addWidget(img_card)

        self.image_compliance_check.toggled.connect(
            lambda on: [b.setEnabled(on) for b in self.sensitivity_buttons.values()]
        )

        # ---- Model / path configuration ----
        model_card = Card()
        model_lay = model_card.layout()
        model_lay.addWidget(SectionLabel("📁 إعدادات مسارات النماذج"))
        for model in MODELS:
            model_lay.addWidget(self._build_model_row(model))
        outer.addWidget(model_card)

        # ---- Language / RTL ----
        lang_card = Card()
        lang_lay = lang_card.layout()
        lang_lay.addWidget(SectionLabel("🌐 اللغة / اتجاه الواجهة"))
        self.language_combo = QComboBox()
        self.language_combo.addItems(["العربية", "English"])
        lang_lay.addWidget(self.language_combo)
        self.language_note = CaptionLabel("يتم تطبيق الاتجاه من اليمين لليسار تلقائياً عند اختيار العربية.")
        lang_lay.addWidget(self.language_note)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        outer.addWidget(lang_card)

        outer.addStretch(1)

    def _build_model_row(self, model: dict) -> QFrame:
        row = Card(flat=True, margins=(12, 10, 12, 10), spacing=6)
        lay = row.layout()

        head = QHBoxLayout()
        name_label = QLabel(model["name"])
        badge = StatusBadge("موجود ✓" if model["found"] else "مفقود ✕", tone="success" if model["found"] else "danger")
        head.addWidget(name_label, 1)
        head.addWidget(badge)
        lay.addLayout(head)

        path_edit = QLineEdit(model["path"])
        path_edit.setPlaceholderText("لم يتم تحديد مسار النموذج")
        lay.addWidget(path_edit)

        guidance = CaptionLabel(
            f"⚠ لم يتم العثور على {model['name']} في هذا المسار. نزّل ملفات النموذج وضعها هنا ثم أعد الفحص."
        )
        recheck_btn = QPushButton("🔍 إعادة الفحص")
        recheck_btn.setProperty("variant", "primary")
        guidance.setVisible(not model["found"])
        recheck_btn.setVisible(not model["found"])

        def do_recheck():
            model["found"] = True
            badge.setText("موجود ✓")
            badge.set_tone("success", self._dark)
            guidance.setVisible(False)
            recheck_btn.setVisible(False)

        recheck_btn.clicked.connect(do_recheck)
        lay.addWidget(guidance)
        lay.addWidget(recheck_btn)

        self._model_rows[model["key"]] = badge
        return row

    def _on_language_changed(self, index: int):
        if index == 0:
            self.language_note.setText("يتم تطبيق الاتجاه من اليمين لليسار تلقائياً عند اختيار العربية.")
        else:
            self.language_note.setText(
                "English is provided for developers/QA — Arabic remains the primary client-facing language."
            )

    def set_dark(self, dark: bool):
        self._dark = dark
        self.internet_panel.set_dark(dark)
        for key, badge in self._model_rows.items():
            model = next(m for m in MODELS if m["key"] == key)
            badge.set_tone("success" if model["found"] else "danger", dark)
