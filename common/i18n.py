"""App-wide Arabic ⇄ English UI language switching for the Hasaballa AI
Platform desktop app.

Arabic is the primary client-facing language; English is provided so
developers/QA (and now end users) can flip the whole UI. This module is
the single source of truth for that toggle:

    from common.i18n import lang_manager, t

    label = QLabel(t("nav.smart_director"))
    lang_manager.changed.connect(self.retranslate)   # live re-translation

Design
------
* `lang_manager` is a process-wide singleton QObject. It holds the current
  language code ("ar" | "en") and emits `changed(code)` whenever it flips.
* Every screen looks its strings up through `t(key)` and implements a
  `retranslate()` slot connected to `lang_manager.changed`. On a flip the
  screen simply re-sets every string from `t(...)` again — the same
  "retranslateUi" pattern Qt Designer generates, done by hand.
* Layout direction is a *view* of the language, not stored separately:
  Arabic → RightToLeft, English → LeftToRight. The app shell reads
  `lang_manager.layout_direction()` on each flip and calls
  `QApplication.setLayoutDirection(...)`, which Qt propagates to every
  existing widget automatically (custom-painted widgets like ToggleSwitch
  read `layoutDirection()` in their paintEvent, so they follow too).

Why raw strings and not Qt's own `.ts`/`tr()` machinery: the rest of this
codebase already stores UI copy as plain Python literals (see every
*_app.py Streamlit source), and the catalog below keeps the Arabic and
English side by side so translators/QA can diff them in one place without
a compile step (`lupdate`/`lrelease`).
"""

from PySide6.QtCore import QObject, Qt, Signal

LANGS = ("ar", "en")


# =====================================================================
# Translation catalog — key -> {"ar": ..., "en": ...}
# Keys are namespaced by screen. Emoji/icons stay in the string so a flip
# never loses them. Add a key here, reference it with t("...") in the UI.
# =====================================================================
TRANSLATIONS = {
    # ---- app shell ----
    "app.brand": {"ar": "حسب الله للذكاء الاصطناعي", "en": "Hasaballa AI"},
    "app.offline_pill": {"ar": "غير متصل — لا يُستخدم الإنترنت", "en": "Offline — no network used"},
    "app.theme_to_dark": {"ar": "الوضع الداكن", "en": "Dark mode"},
    "app.theme_to_light": {"ar": "الوضع الفاتح", "en": "Light mode"},
    # language button shows the language you'll switch TO
    "app.switch_to_en": {"ar": "English", "en": "English"},
    "app.switch_to_ar": {"ar": "العربية", "en": "العربية"},
    "app.not_converted": {
        "ar": "لم يتم تحويلها بعد من Streamlit",
        "en": "Not yet converted from Streamlit",
    },

    # ---- navigation / screen titles ----
    "nav.chat": {"ar": "الدردشة — Hasaballa GPT", "en": "Chat — Hasaballa GPT"},
    "nav.image_animation": {"ar": "تحريك الصور", "en": "Image Animation"},
    "nav.image_generation": {"ar": "توليد الصور", "en": "Image Generation"},
    "nav.character_packs": {"ar": "حزم الشخصيات", "en": "Character Packs"},
    "nav.voice_cloning": {"ar": "الصوت واستنساخه", "en": "Voice & Cloning"},
    "nav.lip_sync": {"ar": "مزامنة الشفاه", "en": "Lip Sync"},
    "nav.audio_layering": {"ar": "الصوت والمكتبة الصوتية", "en": "Audio & Sound Library"},
    "nav.smart_director": {"ar": "المخرج الذكي", "en": "Smart Director"},
    "nav.motion_generation": {"ar": "توليد الحركة", "en": "Motion Generation"},
    "nav.subtitles": {"ar": "الترجمة والدبلجة", "en": "Subtitles & Dubbing"},
    "nav.export": {"ar": "التصدير والعرض", "en": "Export & Preview"},
    "nav.settings": {"ar": "الإعدادات والامتثال", "en": "Settings & Compliance"},
    "nav.publishing": {"ar": "النشر", "en": "Publishing"},

    # ---- settings & compliance screen ----
    "settings.religious.title": {"ar": "🛡️ الامتثال الديني", "en": "🛡️ Religious Compliance"},
    "settings.religious.check": {
        "ar": "حظر تلقائي للصوت غير الملائم دينياً (الموسيقى/العود/الطرب أثناء الأذان أو تلاوة القرآن أو الدعاء)",
        "en": "Automatically block religiously inappropriate audio (music/oud/singing during the adhan, Qur'an recitation, or supplication)",
    },
    "settings.religious.caption": {
        "ar": "مُفعّل تلقائياً في شاشة طبقات الصوت (§7) عند تحديد أن المشهد يحتوي على صوت ديني.",
        "en": "Applied automatically in the Audio Layering screen (§7) when a scene is flagged as containing religious audio.",
    },
    "settings.image.title": {"ar": "🖼️ فلتر الحشمة في الصور", "en": "🖼️ Image Modesty Filter"},
    "settings.image.check": {
        "ar": "رفض تلقائي وإعادة توليد الصور غير الملائمة",
        "en": "Automatically reject and regenerate inappropriate images",
    },
    "settings.image.sensitivity": {"ar": "درجة الحساسية:", "en": "Sensitivity level:"},
    "settings.image.caption": {
        "ar": "درجة حساسية أعلى ترفض تلقائياً المزيد من الصور الحدّية (§3). يُطبَّق بصمت — لا تُعرض الصورة المرفوضة أبداً للمستخدم.",
        "en": "A higher sensitivity automatically rejects more borderline images (§3). Applied silently — a rejected image is never shown to the user.",
    },
    "settings.sensitivity.low": {"ar": "منخفضة", "en": "Low"},
    "settings.sensitivity.medium": {"ar": "متوسطة", "en": "Medium"},
    "settings.sensitivity.high": {"ar": "عالية", "en": "High"},
    "settings.models.title": {"ar": "📁 إعدادات مسارات النماذج", "en": "📁 Model Path Configuration"},
    "settings.models.found": {"ar": "موجود ✓", "en": "Found ✓"},
    "settings.models.missing": {"ar": "مفقود ✕", "en": "Missing ✕"},
    "settings.models.path_placeholder": {
        "ar": "لم يتم تحديد مسار النموذج",
        "en": "No model path set",
    },
    "settings.models.recheck": {"ar": "🔍 إعادة الفحص", "en": "🔍 Re-scan"},
    "settings.lang.title": {"ar": "🌐 اللغة / اتجاه الواجهة", "en": "🌐 Language / UI Direction"},
    "settings.lang.note_ar": {
        "ar": "يتم تطبيق الاتجاه من اليمين لليسار تلقائياً عند اختيار العربية.",
        "en": "Right-to-left direction is applied automatically when Arabic is selected.",
    },
    "settings.lang.note_en": {
        "ar": "الإنجليزية متاحة للمطوّرين والاختبار — تبقى العربية اللغة الأساسية للعميل.",
        "en": "English is provided for developers/QA — Arabic remains the primary client-facing language.",
    },
    # model display names (Arabic source kept the descriptor in Arabic parens)
    "settings.model.sdxl": {"ar": "SDXL / FLUX (توليد الصور)", "en": "SDXL / FLUX (Image Generation)"},
    "settings.model.wan": {"ar": "WAN 2.2 (توليد الحركة)", "en": "WAN 2.2 (Motion Generation)"},
    "settings.model.latentsync": {"ar": "LatentSync (مزامنة الشفاه)", "en": "LatentSync (Lip Sync)"},
    "settings.model.tts": {"ar": "مكتبة الأصوات (TTS)", "en": "Voice Library (TTS)"},
    "settings.model.whisper": {"ar": "Whisper (تحويل الصوت إلى نص)", "en": "Whisper (Speech-to-Text)"},
    "settings.model.nllb": {"ar": "NLLB-200 (الترجمة)", "en": "NLLB-200 (Translation)"},
    "settings.model.missing_guidance": {
        "ar": "⚠ لم يتم العثور على {name} في هذا المسار. نزّل ملفات النموذج وضعها هنا ثم أعد الفحص.",
        "en": "⚠ {name} was not found at this path. Download the model files, place them here, then re-scan.",
    },

    # ---- smart internet access panel ----
    "sia.title": {"ar": "التحكم في الاتصال بالإنترنت", "en": "Internet Access Control"},
    "sia.badge.local": {"ar": "محلي", "en": "Local"},
    "sia.badge.online": {"ar": "متصل", "en": "Online"},
    "sia.badge.cloud": {"ar": "سحابي", "en": "Cloud"},
    "sia.msg.local": {
        "ar": "متصل محلياً فقط — البيانات آمنة تماماً على جهازك",
        "en": "Local only — your data stays fully secure on this device",
    },
    "sia.msg.online": {
        "ar": "الاتصال نشط — مسموح بالبحث الذكي مؤقتاً",
        "en": "Connection active — smart search temporarily allowed",
    },
    "sia.msg.cloud": {"ar": "معالجة سحابية نشطة", "en": "Cloud processing active"},
    "sia.connecting": {"ar": "جارٍ الاتصال…", "en": "Connecting…"},
    "sia.row1.title": {"ar": "الوصول الذكي للإنترنت", "en": "Smart Internet Access"},
    "sia.row1.help": {
        "ar": "بحث مؤقت ومشفّر، دون حفظ سجل التصفح",
        "en": "Temporary encrypted search, no browsing history kept",
    },
    "sia.row2.title": {"ar": "قطع الاتصال والعودة للوضع الآمن", "en": "Disconnect & return to safe mode"},
    "sia.row2.help": {
        "ar": "يُلغي الرموز النشطة فوراً ويعيدك للوضع المحلي",
        "en": "Instantly revokes active tokens and returns you to local mode",
    },
    "sia.disconnect": {"ar": "قطع فوري", "en": "Disconnect now"},
    "sia.row3.title": {"ar": "تحويل خارجي للذكاء الاصطناعي", "en": "External AI Handoff"},
    "sia.row3.help_local": {"ar": "يتطلب تفعيل الوصول للإنترنت أولاً", "en": "Requires internet access to be enabled first"},
    "sia.row3.help_active": {
        "ar": "تتم معالجة هذا الطلب عبر خط أنابيب سحابي مشفّر",
        "en": "This request is processed via an encrypted cloud pipeline",
    },
    "sia.row3.help_idle": {"ar": "يُستخدم فقط عند الحاجة لمعالجة متقدمة", "en": "Used only when advanced processing is needed"},
    "sia.handoff_tag": {"ar": "●  نشط الآن", "en": "●  Active now"},
    "sia.toast": {"ar": "تم حفظ نسخة احتياطية مشفرة للجلسة المحلية", "en": "Encrypted local-session snapshot saved"},
    "sia.footer.lock": {"ar": "🔐 التخزين محلي دائماً", "en": "🔐 Storage is always local"},
    "sia.footer.last_check": {"ar": "آخر تحقق: قبل لحظات", "en": "Last checked: moments ago"},
    "sia.reduced_motion": {"ar": "تقليل الحركة", "en": "Reduce motion"},

    # ---- smart director screen ----
    "sd.subtitle": {
        "ar": "منسّق خط الإنتاج — الوضع التلقائي أو اليدوي عبر كل المشاهد الـ14. لا يوجد محرّك توليد حقيقي موصول؛ هذا يحاكي التوقيت ومعالجة الأعطال.",
        "en": "Pipeline orchestrator — Auto or Manual mode across all 14 scenes. No real generation backend is wired in; this simulates timing and failure handling.",
    },
    "sd.gpu.active": {"ar": "🖥️ المعالج الرسومي: نشط", "en": "🖥️ GPU: Active"},
    "sd.gpu.idle": {"ar": "🖥️ المعالج الرسومي: خامل", "en": "🖥️ GPU: Idle"},

    # stage display names — keyed by stable stage id
    "sd.stage.image": {"ar": "توليد الصور", "en": "Image Generation"},
    "sd.stage.animation": {"ar": "التحريك", "en": "Animation"},
    "sd.stage.voice": {"ar": "الصوت", "en": "Voice"},
    "sd.stage.compilation": {"ar": "التجميع", "en": "Compilation"},

    # now-banner copy (some take .format kwargs)
    "sd.banner.idle": {
        "ar": "خامل — اضبط الوضع وعناصر التخطّي، ثم ابدأ خط الإنتاج.",
        "en": "Idle — configure mode and skip controls, then start the pipeline.",
    },
    "sd.banner.running": {
        "ar": "⏳ جارٍ الآن: المشهد {scene} من {total} — {stage}",
        "en": "⏳ Now processing: Scene {scene} of {total} — {stage}",
    },
    "sd.banner.paused_after_stage": {
        "ar": "⏸ متوقّف مؤقتاً بعد {prev} — اضغط «الخطوة التالية» للمتابعة مع {stage}.",
        "en": "⏸ Paused after {prev} — click Next Step to continue with {stage}.",
    },
    "sd.banner.paused_at_scene": {
        "ar": "⏸ متوقّف مؤقتاً عند المشهد {scene} — {stage}. اضغط «الخطوة التالية» للمتابعة.",
        "en": "⏸ Paused at Scene {scene} — {stage}. Click Next Step to continue.",
    },
    "sd.banner.failed": {
        "ar": "⚠ فشل: المشهد {scene} من {total} — {stage}. المشاهد الـ{done} الأولى سليمة ومكتملة.",
        "en": "⚠ Failed: Scene {scene} of {total} — {stage}. The first {done} scenes are untouched and still complete.",
    },
    "sd.banner.cancelled": {
        "ar": "⛔ أُلغي — {done}/{total} خطوة اكتملت حتى الآن ومحفوظة. يمكنك الاستئناف في أي وقت.",
        "en": "⛔ Cancelled — {done}/{total} steps completed so far are preserved. Resume anytime.",
    },
    "sd.banner.complete": {
        "ar": "🎉 اكتمل خط الإنتاج — كل المشاهد الـ14 جاهزة.",
        "en": "🎉 Pipeline complete — all 14 scenes are ready.",
    },

    "sd.progress.text": {
        "ar": "{done}/{total} خطوة · يتبقّى ~{eta} دقيقة",
        "en": "{done}/{total} steps · ~{eta} min remaining",
    },
    "sd.detail.caption": {
        "ar": "تفاصيل المشهد {scene} (المشهد المعروض حالياً)",
        "en": "Detail for Scene {scene} (the scene currently in view)",
    },
    "sd.mode.label": {"ar": "الوضع", "en": "Mode"},
    "sd.mode.auto": {"ar": "🤖 تلقائي", "en": "🤖 Auto"},
    "sd.mode.manual": {"ar": "🧑‍💻 يدوي", "en": "🧑‍💻 Manual"},
    "sd.mode.caption": {
        "ar": "الوضع اليدوي يتوقّف بعد كل مرحلة لمراجعتها قبل المتابعة. الوضع التلقائي يعمل دون توقّف.",
        "en": "Manual mode pauses after every stage so you can review before continuing. Auto runs straight through.",
    },
    "sd.skip.label": {"ar": "تخطّي حسب المرحلة", "en": "Per-Stage Skip"},
    "sd.queue.label": {"ar": "قائمة المشاهد — 14 مشهداً", "en": "Scene Queue — 14 Scenes"},
    "sd.timeline.title": {"ar": "🗂️ الجدول الزمني للمهام", "en": "🗂️ Task Timeline"},
    "sd.scene": {"ar": "المشهد {n}", "en": "Scene {n}"},
    "sd.logs.title": {"ar": "📜 السجل", "en": "📜 Logs"},
    "sd.logs.cleared": {"ar": "— تم مسح السجل —", "en": "— log cleared —"},
    "sd.logs.clear": {"ar": "مسح", "en": "Clear"},

    # action buttons
    "sd.btn.start": {"ar": "▶ بدء خط الإنتاج", "en": "▶ Start Pipeline"},
    "sd.btn.pause": {"ar": "⏸ إيقاف مؤقت", "en": "⏸ Pause"},
    "sd.btn.cancel": {"ar": "⛔ إلغاء", "en": "⛔ Cancel"},
    "sd.btn.next": {"ar": "▶ الخطوة التالية", "en": "▶ Next Step"},
    "sd.btn.retry": {"ar": "↻ إعادة المحاولة", "en": "↻ Retry"},
    "sd.btn.skip_scene": {"ar": "⏭ تخطّي المشهد", "en": "⏭ Skip Scene"},
    "sd.btn.abort": {"ar": "⛔ إنهاء", "en": "⛔ Abort"},
    "sd.btn.resume": {"ar": "▶ استئناف خط الإنتاج", "en": "▶ Resume Pipeline"},
    "sd.btn.restart": {"ar": "🔄 بدء من جديد", "en": "🔄 Start Fresh"},
    "sd.btn.new_batch": {"ar": "🔄 دفعة جديدة", "en": "🔄 Start New Batch"},
    "sd.failed.prompt": {
        "ar": "فشلت المرحلة عند المشهد {scene} — {stage}. اختر كيفية المتابعة:",
        "en": "Stage failed at Scene {scene} — {stage}. Choose how to proceed:",
    },

    # log lines
    "sd.log.start": {"ar": "بدأ خط الإنتاج في الوضع {mode}.", "en": "Pipeline started in {mode} mode."},
    "sd.log.done": {"ar": "✓ اكتمل: المشهد {scene} — {stage}", "en": "✓ Done: Scene {scene} — {stage}"},
    "sd.log.skip_stage": {"ar": "– تم تخطّي المرحلة بالكامل: {stage}", "en": "– Stage skipped entirely: {stage}"},
    "sd.log.fail": {"ar": "✕ فشل: المشهد {scene} — {stage}", "en": "✕ Failed: Scene {scene} — {stage}"},
    "sd.log.retry": {"ar": "↻ إعادة محاولة المشهد {scene} — {stage}", "en": "↻ Retrying Scene {scene} — {stage}"},
    "sd.log.skip_scene": {"ar": "⏭ تم تخطّي المشهد {scene} — {stage}", "en": "⏭ Skipped Scene {scene} — {stage}"},
    "sd.log.pause": {"ar": "⏸ تم الإيقاف المؤقت.", "en": "⏸ Paused."},
    "sd.log.resume": {"ar": "▶ استئناف.", "en": "▶ Resumed."},
    "sd.log.cancel": {"ar": "⛔ أُلغي خط الإنتاج.", "en": "⛔ Pipeline cancelled."},
    "sd.log.complete": {"ar": "🎉 اكتمل خط الإنتاج — كل المشاهد جاهزة.", "en": "🎉 Pipeline complete — all scenes ready."},
    "sd.log.reset": {"ar": "🔄 تمت إعادة الضبط. جاهز للبدء.", "en": "🔄 Reset. Ready to start."},
    "sd.mode.auto_word": {"ar": "التلقائي", "en": "Auto"},
    "sd.mode.manual_word": {"ar": "اليدوي", "en": "Manual"},
}


class LanguageManager(QObject):
    """Process-wide singleton holding the current UI language."""

    changed = Signal(str)  # emits the new language code ("ar" | "en")

    def __init__(self):
        super().__init__()
        self._lang = "ar"  # Arabic is the primary client-facing language

    @property
    def lang(self) -> str:
        return self._lang

    def is_rtl(self) -> bool:
        return self._lang == "ar"

    def layout_direction(self) -> Qt.LayoutDirection:
        return Qt.RightToLeft if self.is_rtl() else Qt.LeftToRight

    def set_lang(self, lang: str):
        if lang not in LANGS or lang == self._lang:
            return
        self._lang = lang
        self.changed.emit(lang)

    def toggle(self):
        self.set_lang("en" if self._lang == "ar" else "ar")

    def t(self, key: str, **kwargs) -> str:
        entry = TRANSLATIONS.get(key)
        if entry is None:
            text = key  # surfaces missing keys loudly instead of silently blanking
        else:
            text = entry.get(self._lang) or entry.get("ar") or key
        return text.format(**kwargs) if kwargs else text


# The one instance every screen imports.
lang_manager = LanguageManager()


def t(key: str, **kwargs) -> str:
    """Shorthand for lang_manager.t(...). Import this in every screen."""
    return lang_manager.t(key, **kwargs)
