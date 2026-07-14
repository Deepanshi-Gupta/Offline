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
    "app.online_pill": {"ar": "متصل — الوصول الذكي نشط", "en": "Online — Smart Access active"},
    "app.cloud_pill": {"ar": "معالجة سحابية نشطة", "en": "Cloud processing active"},
    "app.connecting_pill": {"ar": "جارٍ الاتصال…", "en": "Connecting…"},
    "app.smart_access_toggle_tooltip": {"ar": "الوصول الذكي للإنترنت", "en": "Smart Internet Access"},
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
    "nav.smart_internet_access": {"ar": "الوصول الذكي للإنترنت", "en": "Smart Internet Access"},
    "sia.screen.subtitle": {
        "ar": "معاينة مستقلة للوحة التحكم في الاتصال — نفس المكوّن المُضمَّن في الإعدادات (§14).",
        "en": "Standalone preview of the connection-control panel — the same component embedded in Settings (§14).",
    },

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

    # ---- image animation screen ----
    "ia.desc.placeholder": {"ar": "صف الحركة المطلوبة...", "en": "Describe the animation..."},
    "ia.toggle.full_body": {"ar": "تحريك الجسم الكامل", "en": "Full Body Animation"},
    "ia.toggle.bg_motion": {"ar": "حركة الخلفية", "en": "Background Motion"},
    "ia.toggle.lip_sync": {"ar": "مزامنة الشفاه", "en": "Lip Sync"},
    "ia.section.face_detection": {"ar": "كشف الوجوه", "en": "Face Detection"},
    "ia.face.label": {"ar": "وجه {n}", "en": "Face {n}"},
    "ia.section.assign_voice": {"ar": "تعيين صوت للوجه", "en": "Assign Voice to Face"},
    "ia.btn.skip": {"ar": "⏭️  تخطّي", "en": "⏭️  Skip"},
    "ia.btn.generate": {"ar": "توليد الفيديو", "en": "Generate Video"},

    # ---- chat / Hasaballa GPT screen ----
    "chat.msg_empty": {
        "ar": "لا توجد رسائل بعد — اكتب سيناريو أدناه للبدء.",
        "en": "No messages yet — type a scenario below to begin.",
    },
    "chat.script_placeholder": {"ar": "اكتب هنا السيناريو...", "en": "Type your scenario here..."},
    "chat.char_counter": {"ar": "{n} / {max}", "en": "{n} / {max}"},
    "chat.mic_recording": {"ar": "جارٍ التسجيل...", "en": "Recording…"},
    "chat.mic_error": {
        "ar": "🎤 الميكروفون غير متاح — تحقق من جهاز الإدخال في الإعدادات.",
        "en": "🎤 Microphone unavailable — check your input device in Settings.",
    },
    "chat.mic_transcribed_suffix": {
        "ar": " [نص محوّل من الصوت — ميزة تحويل الصوت التجريبية]",
        "en": " [transcribed from voice — experimental speech-to-text]",
    },
    "chat.attach.image": {"ar": "🖼️ صورة مرجعية", "en": "🖼️ Reference image"},
    "chat.attach.audio": {"ar": "🎵 صوت مرجعي", "en": "🎵 Reference audio"},
    "chat.btn.manual": {"ar": "🎬 توليد يدوي", "en": "🎬 Manual Generate"},
    "chat.btn.auto": {"ar": "✨ توليد تلقائي", "en": "✨ Auto Generate"},
    "chat.warn.no_scenario": {"ar": "لم يتم إدخال سيناريو — لا شيء لتوليده.", "en": "No scenario entered — nothing to generate."},
    "chat.result_msg": {
        "ar": "✅ تم استلام السيناريو ({n} حرف) · {ratio} · وضع {mode} — بدأ التنفيذ. راقب التقدم في المخرج الذكي.",
        "en": "✅ Scenario received ({n} chars) · {ratio} · {mode} mode — execution started. Watch progress in Smart Director.",
    },
    "chat.mode.manual": {"ar": "يدوي", "en": "Manual"},
    "chat.mode.auto": {"ar": "تلقائي", "en": "Auto"},
    "chat.folder_tooltip": {"ar": "المشاريع المحفوظة", "en": "Saved Projects"},
    "chat.saved_projects.title": {"ar": "📁 المشاريع المحفوظة", "en": "📁 Saved Projects"},
    "chat.saved_projects.empty": {"ar": "لا توجد مشاريع محفوظة بعد.", "en": "No saved projects yet."},
    "chat.saved_projects.open": {"ar": "فتح", "en": "Open"},
    "chat.saved_projects.delete": {"ar": "حذف", "en": "Delete"},
    "chat.saved_projects.would_open": {"ar": "سيتم فتح '{name}'.", "en": "Would open '{name}'."},
    "chat.sidebar.image_generation": {"ar": "توليد الصور", "en": "Generate images"},
    "chat.sidebar.voice_cloning": {"ar": "استنساخ الأصوات المرجعية", "en": "Clone reference voices"},
    "chat.sidebar.audio_enhance": {"ar": "تحسين جودة الصوت", "en": "Enhance audio quality"},
    "chat.sidebar.audio_generate": {"ar": "توليد الصوت", "en": "Generate audio"},
    "chat.sidebar.lip_sync": {"ar": "تحريك الصور ومزامنة الشفاه", "en": "Image Animation & Lip sync"},
    "chat.sidebar.inpainting": {"ar": "ترميم ذكي انتقائي", "en": "Selective smart inpainting"},
    "chat.sidebar.timeline": {"ar": "الجدول الزمني", "en": "Timeline"},
    "chat.sidebar.would_open": {"ar": "سيتم فتح: {label}", "en": "Would open: {label}"},
    "chat.sidebar.not_built": {"ar": "سيتم فتح: {label} (لم يُبنَ بعد)", "en": "Would open: {label} (not built yet)"},
    "chat.debug.mic_unavailable": {"ar": "محاكاة: الميكروفون غير متاح", "en": "Simulate: microphone unavailable"},
    "chat.remove_tooltip": {"ar": "إزالة", "en": "Remove"},
    "chat.play_tooltip": {"ar": "تشغيل", "en": "Play"},

    # ---- image generation screen (§3) ----
    "img.prompt.label": {"ar": "الوصف (بالعربية)", "en": "Prompt (Arabic)"},
    "img.seed.label": {"ar": "البذرة (Seed)", "en": "Seed"},
    "img.seed.lock": {"ar": "قفل البذرة", "en": "Lock seed"},
    "img.ref_slot": {"ar": "منفذ صورة مرجعية للشخصية", "en": "Character reference-image slot"},
    "img.ref_slot.caption": {
        "ar": "يُستخدم للحفاظ على هوية الشخصية عبر الدفعة.",
        "en": "Used to keep the same character identity across the batch.",
    },
    "img.style_refs": {"ar": "صور مرجعية للأسلوب ({n})", "en": "Style Reference Images ({n})"},
    "img.arabic_text": {"ar": "نص عربي", "en": "Arabic Text"},
    "img.batch.title": {"ar": "الدفعة — 14 مشهداً", "en": "Batch — 14 Scenes"},
    "img.batch.generate": {"ar": "توليد دفعة الـ14 مشهداً", "en": "Generate 14-Scene Batch"},
    "img.batch.cancel": {"ar": "إلغاء", "en": "Cancel"},
    "img.batch.empty": {
        "ar": "لم يتم توليد أي دفعة بعد. حدّد البذرة واضغط توليد دفعة الـ14 مشهداً لإنشاء شبكة المشاهد.",
        "en": "No batch generated yet. Set a seed and click Generate 14-Scene Batch to create the scene grid.",
    },
    "img.scene": {"ar": "مشهد {n}", "en": "Scene {n}"},
    "img.status.queued": {"ar": "قيد الانتظار", "en": "Queued"},
    "img.status.generating": {"ar": "جارٍ التوليد…", "en": "Generating…"},
    "img.status.compliance": {"ar": "🛡️ فحص الامتثال\nجارٍ التعديل…", "en": "🛡️ Compliance check\nadjusting image…"},
    "img.status.failed": {"ar": "⚠ فشل", "en": "⚠ Failed"},
    "img.status.manual_review": {"ar": "🚩 يحتاج\nمراجعة يدوية", "en": "🚩 Needs\nmanual review"},
    "img.status.skipped": {"ar": "تم التخطي", "en": "Skipped"},
    "img.approved": {"ar": "✓ مقبول", "en": "✓ Approved"},
    "img.rejected": {"ar": "✕ مرفوض", "en": "✕ Rejected"},
    "img.btn.approve": {"ar": "✓", "en": "✓"},
    "img.btn.reject": {"ar": "✕", "en": "✕"},
    "img.btn.regenerate": {"ar": "↻ إعادة التوليد", "en": "↻ Regenerate"},
    "img.btn.retry": {"ar": "إعادة المحاولة", "en": "Retry"},
    "img.summary": {
        "ar": "{success} نجح · {approved} مقبول · {failed} بحاجة لإعادة المحاولة · {review} بحاجة لمراجعة يدوية · {skipped} تم تخطّيه",
        "en": "{success} succeeded · {approved} approved · {failed} need retry · {review} need manual review · {skipped} skipped",
    },
    "img.manual_review.title": {"ar": "🚩 بحاجة لمراجعة يدوية", "en": "🚩 Manual Review Needed"},
    "img.manual_review.desc": {
        "ar": "المشهد {n} — رفض متكرر بسبب الامتثال، لا تُعرض صورة لمشهد تم الإبلاغ عنه.",
        "en": "Scene {n} — repeated compliance rejection, no image is shown for a flagged scene.",
    },
    "img.btn.edit_prompt": {"ar": "✏️ تعديل الوصف", "en": "✏️ Edit Prompt"},
    "img.btn.skip": {"ar": "⏭️ تخطّي", "en": "⏭️ Skip"},
    "img.regen_dialog.title": {"ar": "إعادة توليد المشهد", "en": "Regenerate Scene"},
    "img.regen_dialog.withheld": {
        "ar": "تم حجب هذا المشهد للمراجعة اليدوية — لا تُعرض معاينة لصورة مُبلَّغ عنها.",
        "en": "This scene was withheld for manual review — no preview is shown for a flagged image.",
    },
    "img.regen_dialog.prompt": {"ar": "تجاوز الوصف (اختياري)", "en": "Prompt override (optional)"},
    "img.regen_dialog.prompt_ph": {"ar": "اتركه فارغًا لاستخدام نفس الوصف", "en": "Leave empty to use the same prompt"},
    "img.regen_dialog.seed": {"ar": "تجاوز البذرة", "en": "Seed override"},
    "img.regen_dialog.confirm": {"ar": "تأكيد إعادة التوليد", "en": "Confirm Regenerate"},
    "img.regen_dialog.cancel": {"ar": "إلغاء", "en": "Cancel"},

    # ---- character pack manager screen (§4) ----
    "cp.subtitle": {
        "ar": "8 صور مرجعية لكل شخصية، ترجيح لكل صورة، وصوت مقترن — يطابق تصدير/استيراد JSON.",
        "en": "8 reference images per character, per-image weighting, and a paired voice — matches JSON import/export.",
    },
    "cp.btn.add": {"ar": "+ إضافة شخصية", "en": "+ Add Character"},
    "cp.btn.import": {"ar": "استيراد JSON", "en": "Import JSON"},
    "cp.btn.export": {"ar": "⬇ تصدير JSON", "en": "⬇ Export JSON"},
    "cp.empty": {
        "ar": "لا توجد شخصيات بعد — اضغط + إضافة شخصية لإنشاء أول حزمة شخصية.",
        "en": "No characters yet — click + Add Character to create your first character pack.",
    },
    "cp.status.empty": {"ar": "لا توجد صور بعد", "en": "No images yet"},
    "cp.status.incomplete": {"ar": "غير مكتمل", "en": "Incomplete"},
    "cp.status.complete": {"ar": "مكتمل", "en": "Complete"},
    "cp.status.conflict": {"ar": "تعارض في الهوية", "en": "Identity conflict"},
    "cp.images_count": {"ar": "{filled}/{total} صور", "en": "{filled}/{total} images"},
    "cp.images_count_full": {"ar": "{filled}/{total} صور مرجعية", "en": "{filled}/{total} reference images"},
    "cp.voice_label": {"ar": "الصوت: {voice}", "en": "Voice: {voice}"},
    "cp.conflict_warning": {
        "ar": "⚠ الفتحتان {a} و{b} تستخدمان نفس الصورة تماماً.",
        "en": "⚠ Slots {a} and {b} use the identical image.",
    },
    "cp.btn.edit": {"ar": "تعديل", "en": "Edit"},
    "cp.btn.remove": {"ar": "إزالة", "en": "Remove"},
    "cp.btn.back": {"ar": "← العودة لقائمة الشخصيات", "en": "← Back to Character List"},
    "cp.name.label": {"ar": "اسم الشخصية", "en": "Character name"},
    "cp.voice.label": {"ar": "الصوت المقترن", "en": "Paired voice"},
    "cp.slots.title": {"ar": "الصور المرجعية (8 فتحات)", "en": "Reference Images (8 slots)"},
    "cp.slot.empty": {"ar": "+ فتحة {n}", "en": "+ Slot {n}"},
    "cp.slot.caption": {"ar": "فتحة {n} · وزن {w}", "en": "Slot {n} · weight {w}"},
    "cp.import.success": {"ar": "تم استيراد {n} شخصية.", "en": "Imported {n} character(s)."},
    "cp.import.failed": {"ar": "فشل الاستيراد — ملف JSON غير صالح: {err}", "en": "Import failed — invalid character pack JSON: {err}"},

    # ---- voice / TTS & voice cloning screen (§5) ----
    "voice.subtitle": {
        "ar": "لا يوجد نموذج TTS/استنساخ صوت محلي موصول بعد — الصوت المولّد والمستنسخ أدناه نغمات مؤقتة فقط.",
        "en": "No local TTS/voice-cloning model is wired in yet — generated and cloned audio below are placeholder tones, not real speech.",
    },
    "voice.sec.a.title": {"ar": "أ - أصوات مرجعية لعدة شخصيات", "en": "A - Reference Voices for Multiple Characters"},
    "voice.character": {"ar": "الشخصية {n}", "en": "Character {n}"},
    "voice.speaking_as": {"ar": "التحدّث بصوت", "en": "Speaking as"},
    "voice.tts_text_ph": {"ar": "أدخل النص لتحويله إلى كلام...", "en": "Enter text to convert to speech..."},
    "voice.btn.generate": {"ar": "توليد الصوت", "en": "Generate Voice"},
    "voice.warn.no_text": {"ar": "لم يتم إدخال نص — لا شيء لتوليده.", "en": "No text entered — nothing to generate."},
    "voice.warn.unsupported": {
        "ar": "عيّنة معاينة {voice} غير جاهزة بعد — قد تكون جودة التوليد منخفضة.",
        "en": "{voice}'s preview sample isn't ready yet — generation quality may be low.",
    },
    "voice.generated_caption": {"ar": "تم التوليد — الصوت: {voice}", "en": "Generated — voice: {voice}"},
    "voice.ref_audio_ph": {"ar": "صوت مرجعي (للاستنساخ)", "en": "Reference audio (cloning)"},
    "voice.btn.clone": {"ar": "استنساخ الصوت 🎙️", "en": "Clone Voice 🎙️"},
    "voice.warn.no_ref": {"ar": "ارفع ملف صوت مرجعي قبل الاستنساخ.", "en": "Upload a reference audio file before cloning."},
    "voice.cloned_caption": {"ar": "صوت مستنسخ — تطابق 100% مع الهدف (صوت مؤقت)", "en": "Cloned voice — 100% match target (placeholder audio)"},
    "voice.sec.g.title": {"ar": "ز - مكتبة الأصوات الكاملة — 12 نوعاً", "en": "G - Full Voice Library — 12 Voice Types"},
    "voice.sec.g.desc": {
        "ar": "مكتبة أصوات كاملة — بالعربية (كل اللهجات) والإنجليزية — تُستخدم عند عدم توفر صوت مرجعي.",
        "en": "A full voice library — in Arabic (all dialects) & English — used when no reference audio is provided.",
    },
    "voice.btn.preview": {"ar": "▶ معاينة", "en": "▶ Preview"},
    "voice.preview_unavailable": {"ar": "معاينة الصوت غير متاحة بعد — المكتبة لا تزال قيد الإعداد.", "en": "Audio preview unavailable yet — library still being curated."},
    "voice.sec.dialect.title": {"ar": "منتقي اللهجات — 21 لهجة عربية", "en": "Dialect Selector — 21 Arabic Dialects"},
    "voice.sec.dialect.desc": {
        "ar": "ليست كل اللهجات بنفس جودة التحويل الصوتي حتى الآن — معروضة هنا بصدق، لا كأنها متكافئة.",
        "en": "Not every dialect has equal TTS quality yet — shown honestly below, not presented as equivalent.",
    },
    "voice.active_dialect": {"ar": "اللهجة النشطة", "en": "Active dialect"},
    "voice.dialect_warning": {
        "ar": "جودة التحويل الصوتي للهجة '{dialect}' حالياً {quality} — توقّع نتائج أقل دقة.",
        "en": "'{dialect}' currently has {quality} TTS quality — expect rougher output.",
    },
    "voice.quality.high": {"ar": "عالية", "en": "high"},
    "voice.quality.medium": {"ar": "متوسطة", "en": "medium"},
    "voice.quality.low": {"ar": "منخفضة", "en": "low"},
    "voice.quality.unsupported": {"ar": "غير مدعومة", "en": "unsupported"},
    "voice.quality.high_label": {"ar": "جودة عالية", "en": "High quality"},
    "voice.quality.medium_label": {"ar": "جودة متوسطة", "en": "Medium quality"},
    "voice.quality.low_label": {"ar": "جودة منخفضة", "en": "Low quality"},
    "voice.quality.unsupported_label": {"ar": "المعاينة غير متاحة", "en": "Preview unavailable"},
    "voice.sec.speed.title": {"ar": "التحكم في سرعة الصوت", "en": "Voice Speed Control"},
    "voice.speed.slow": {"ar": "بطيء", "en": "Slow"},
    "voice.speed.normal": {"ar": "عادي", "en": "Normal"},
    "voice.speed.fast": {"ar": "سريع", "en": "Fast"},
    "voice.speed.sprint": {"ar": "سباق", "en": "Sprint"},
    "voice.speed.custom": {"ar": "مخصّص", "en": "Custom"},
    "voice.speed.caption": {
        "ar": "×{speed} ({preset}) — أوامر النص المضمّنة `[[voice.speed=X]]` تبقى متزامنة مع هذا التحكم.",
        "en": "{speed}× ({preset}) — inline `[[voice.speed=X]]` script commands stay in sync with this control.",
    },
    "voice.sec.s.title": {"ar": "س - تحسين استوديو للصوت", "en": "S - Studio-like Audio Enhancement"},
    "voice.sec.s.desc": {"ar": "إزالة ضجيج الخلفية وتحسين وضوح الصوت.", "en": "Remove background noise and boost voice clarity."},
    "voice.btn.enhance": {"ar": "تحسين الصوت", "en": "Enhance Voice"},
    "voice.enhance_done": {"ar": "اكتمل التحسين (مؤقت — لا يوجد خط أنابيب Demucs موصول هنا).", "en": "Enhancement complete (placeholder — no Demucs pipeline wired in here)."},
    "voice.sec.7.title": {"ar": "٧ - استنساخ الصوت - يتطلب تطابق 100%", "en": "7 - Voice Cloning - 100% Match Required"},
    "voice.sec.7.desc": {"ar": "دعم التنفّس الطبيعي، الصمت الواقعي، وتنويعات النبرة.", "en": "Support natural breathing, realistic silence, and tone variations."},
    "voice.sec.8a.title": {"ar": "أ - دعم جميع اللهجات العربية", "en": "A - All Arabic Dialects Supported"},
    "voice.sec.8a.desc": {
        "ar": "يجب دعم جميع اللهجات العربية بدقة وبشكل طبيعي — راجع منتقي اللهجات أعلاه للقائمة الكاملة وتقييمات الجودة الصادقة.",
        "en": "All Arabic dialects must be supported accurately and naturally — see the Dialect Selector above for the full list and honest quality ratings.",
    },
    "voice.sec.f.title": {"ar": "و - توليد صوت غير مستنسخ (من المكتبة)", "en": "F - Non-Cloned Voice Generation (Library-based)"},
    "voice.sec.f.desc": {"ar": "استخدام مكتبة الأصوات الداخلية عند عدم توفر صوت مرجعي.", "en": "Use internal Voice Library when no reference voice is provided."},
    "voice.btn.library_generate": {"ar": "توليد من المكتبة 📚", "en": "Generate Voice from Library 📚"},
    "voice.sec.g2.title": {"ar": "ز - مكتبة الأصوات الكاملة بالعربية والإنجليزية", "en": "G - Full Voice Library in Arabic & English"},
    "voice.sec.g2.desc": {
        "ar": "أصوات احتياطية افتراضية بالعربية والإنجليزية للصوتيات المرجعية غير المدعومة — راجع متصفح مكتبة الأصوات أعلاه لكل الأنواع الـ12.",
        "en": "Default fallback voices in Arabic & English for unsupported reference audios — see the Voice Library Browser above for all 12 voice types.",
    },
    "voice.sec.h.title": {"ar": "ح - استخدام الأصوات المرجعية في الصوت الخلفي", "en": "H - Use Reference Voices in Background Audio"},
    "voice.sec.h.desc": {
        "ar": "الكشف التلقائي عن الأصوات المرجعية في الطبقات الخلفية وتعيينها بشكل صحيح.",
        "en": "Auto-detect reference voices in background layers and assign them correctly.",
    },
    "voice.match_reference": {"ar": "مطابقة الصوت المرجعي", "en": "Match reference audio"},
    "voice.fallback_audio": {"ar": "استخدام البديل المستنسخ/المولّد", "en": "Use cloned/generated fallback"},
    "voice.skip_caption": {"ar": "إذا تم تحديدها، تُتجاهل هذه المرحلة أثناء توليد الفيديو دون توقف.", "en": "If selected, this stage is ignored during video generation without interruption."},
    "voice.btn.skip_step": {"ar": "تخطّي هذه الخطوة", "en": "Skip This Step"},

    # ---- lip sync screen (§6) ----
    "lip.subtitle": {
        "ar": "يعيش هذا التحكم داخل لوحة خصائص المقطع في الجدول الزمني — معروض هنا كشاشة مستقلة. لا يوجد نموذج LatentSync موصول؛ الإصدارات محاكاة.",
        "en": "Lives inside a timeline clip's properties panel — shown here as its own screen. No LatentSync model is wired in; renders are simulated.",
    },
    "lip.clip.label": {"ar": "المقطع", "en": "Clip"},
    "lip.status.not_applied": {"ar": "لم يُطبَّق", "en": "Not Applied"},
    "lip.status.processing": {"ar": "قيد المعالجة…", "en": "Processing…"},
    "lip.status.applied": {"ar": "مُطبَّق ✓", "en": "Applied ✓"},
    "lip.status.failed": {"ar": "فشل — تم اكتشاف انحراف", "en": "Failed — Drift Detected"},
    "lip.talking.title": {"ar": "كشف isTalking", "en": "isTalking Detection"},
    "lip.talking.desc": {
        "ar": "يُكتشف تلقائياً من مسار الحوار — مزامنة الشفاه تُفعَّل تلقائياً فقط للشخصيات المُصنَّفة على أنها تتحدث.",
        "en": "Auto-detected from the dialogue track — lip sync only auto-activates for characters flagged as talking.",
    },
    "lip.talking": {"ar": "🗣️ يتحدث", "en": "🗣️ Talking"},
    "lip.silent": {"ar": "صامت", "en": "Silent"},
    "lip.btn.redetect": {"ar": "🔄 إعادة الكشف", "en": "🔄 Re-detect"},
    "lip.mode.title": {"ar": "وضع الإصدار", "en": "Rendering Mode"},
    "lip.mode.natural": {"ar": "طبيعي", "en": "Natural"},
    "lip.mode.radio": {"ar": "راديو", "en": "Radio"},
    "lip.mode.phone": {"ar": "هاتف", "en": "Phone"},
    "lip.mode.megaphone": {"ar": "مكبّر صوت", "en": "Megaphone"},
    "lip.mode.natural_desc": {"ar": "حركة فم واقعية افتراضية مطابقة لصوت الحوار.", "en": "Default realistic lip movement matched to dialogue audio."},
    "lip.mode.radio_desc": {"ar": "حركة فم بسيطة — أسلوب تعليق صوتي خارج الكادر.", "en": "Minimal mouth movement — voice-over / off-camera narration style."},
    "lip.mode.phone_desc": {"ar": "إطار مكالمة هاتفية مقيّد — حركة خفيفة للقطات القريبة من الجهاز.", "en": "Constrained, phone-call framing — subtle motion for device close-ups."},
    "lip.mode.megaphone_desc": {"ar": "حركة فم مبالغ فيها ومضخّمة للإلقاء الصاخب/الصراخ.", "en": "Exaggerated, amplified mouth motion for loud/shouting delivery."},
    "lip.pending_note": {
        "ar": "تغيير معلَّق: {pending} (المُطبَّق حالياً: {applied}) — لم تتم إعادة الإصدار بعد.",
        "en": "Pending change: {pending} (currently applied: {applied}) — not re-rendered yet.",
    },
    "lip.none": {"ar": "لا شيء", "en": "none"},
    "lip.btn.apply": {"ar": "▶ تطبيق / إعادة الإصدار", "en": "▶ Apply / Re-render"},
    "lip.failed_desc": {
        "ar": "تم اكتشاف انحراف أثناء إصدار وضع {mode} — خرجت مزامنة الفم عن التوافق في منتصف العملية.",
        "en": "Drift detected while rendering {mode} mode — mouth sync fell out of alignment partway through.",
    },
    "lip.btn.retry_render": {"ar": "↻ إعادة الإصدار مجدداً", "en": "↻ Re-render again"},
    "lip.preview.title": {"ar": "معاينة المزامنة", "en": "Sync Preview"},
    "lip.preview.synced": {"ar": "تمت المزامنة بوضع {mode}.", "en": "Synced with {mode} mode."},
    "lip.btn.play_preview": {"ar": "▶ تشغيل المعاينة", "en": "▶ Play Preview"},
    "lip.preview.rendering": {"ar": "الإصدار قيد التقدّم…", "en": "Rendering in progress…"},
    "lip.preview.failed": {"ar": "لا توجد معاينة صالحة — فشل آخر إصدار في اكتشاف الانحراف.", "en": "No usable preview — last render failed drift detection."},
    "lip.preview.not_applied": {"ar": "لم يُطبَّق بعد — اختر وضعاً أعلاه واضغط تطبيق / إعادة الإصدار.", "en": "Not applied yet — pick a mode above and click Apply / Re-render."},
    "lip.dialog.title": {"ar": "تأكيد إعادة الإصدار", "en": "Confirm Re-render"},
    "lip.dialog.warning": {
        "ar": "يحتوي هذا المقطع حالياً على مزامنة {current}. التبديل إلى {target} يتطلب إعادة إصدار كاملة — قد يستغرق ذلك أكثر من 45 ثانية على مقطع كامل.",
        "en": "This clip currently has {current} lip sync. Switching to {target} requires a full re-render — this can take 45+ seconds on a full clip.",
    },
    "lip.dialog.confirm": {"ar": "تأكيد إعادة الإصدار", "en": "Confirm Re-render"},
    "lip.dialog.cancel": {"ar": "إلغاء", "en": "Cancel"},

    # ---- audio layering & sound library screen (§7) ----
    "audio.subtitle": {
        "ar": "كل عينة أدناه نغمة مؤقتة مُصنَّعة — لا يوجد محرك صوت أو مكتبة صوتية حقيقية موصولة.",
        "en": "Every sample below is a synthesized placeholder tone — no real sound library or audio engine is wired in.",
    },
    "audio.compliance.title": {"ar": "🛡️ الامتثال الديني", "en": "🛡️ Religious Compliance"},
    "audio.compliance.enabled": {"ar": "فلتر الامتثال مُفعَّل", "en": "Compliance filter enabled"},
    "audio.compliance.sacred": {"ar": "المشهد يحتوي على أذان / تلاوة قرآن / دعاء", "en": "Scene contains Adhan / Qur'an recitation / Dua"},
    "audio.compliance.blocked_note": {
        "ar": "🚫 {blocked} من {total} أصل محظور لهذا المشهد — لا موسيقى أو عود أو طرب أثناء الصوت المقدّس.",
        "en": "🚫 {blocked} of {total} assets blocked for this scene — no music, oud, or tarab during sacred audio.",
    },
    "audio.compliance.ok_note": {
        "ar": "لا يوجد صوت مقدّس في هذا المشهد حالياً — أصول الموسيقى/العود/الطرب مسموحة. تفعيل المفتاح أعلاه يحظرها تلقائياً.",
        "en": "No sacred audio in this scene right now — music/oud/tarab assets are allowed. Enabling the toggle above blocks them automatically.",
    },
    "audio.compliance.off_note": {
        "ar": "فلتر الامتثال متوقف — لا يتم حظر أي شيء. غير مستحسن للمشاهد التي تحتوي على صوت مقدّس.",
        "en": "Compliance filter is off — nothing is being blocked. Not recommended for scenes with sacred audio.",
    },
    "audio.library.title": {"ar": "📚 مكتبة الأصوات — 16 فئة", "en": "📚 Sound Library — 16 Categories"},
    "audio.category.label": {"ar": "الفئة", "en": "Category"},
    "audio.search.ph": {"ar": "ابحث في هذه الفئة…", "en": "Search this category…"},
    "audio.category.empty": {
        "ar": "{cat} لم تُملأ بعد — 0 من الهدف 50+ عينة. هذا هو الوضع الفعلي حالياً، وليس خطأً.",
        "en": "{cat} hasn't been populated yet — 0 of the target 50+ samples curated. This is the real state today, not a bug.",
    },
    "audio.no_match": {"ar": "لا توجد عينات مطابقة لبحثك في هذه الفئة.", "en": "No samples match your search in this category."},
    "audio.btn.preview": {"ar": "▶ معاينة", "en": "▶ Preview"},
    "audio.btn.add_to_mix": {"ar": "+ إضافة للمزيج", "en": "+ Add to Mix"},
    "audio.blocked_note": {"ar": "🚫 محظور — {reason}", "en": "🚫 Blocked — {reason}"},
    "audio.blocked_reason": {
        "ar": "امتثال الصوت المقدّس — لا موسيقى/عود/طرب أثناء الأذان أو تلاوة القرآن أو الدعاء.",
        "en": "Sacred audio compliance — no music/oud/tarab during Adhan, Qur'an recitation, or Dua.",
    },
    "audio.added_toast": {"ar": "تمت إضافة '{name}' إلى {track}.", "en": "Added '{name}' to {track}."},
    "audio.mixer.title": {"ar": "🎚️ طبقات الصوت / المازج", "en": "🎚️ Audio Layering / Mixer"},
    "audio.track.mute": {"ar": "كتم", "en": "Mute"},
    "audio.track.solo": {"ar": "منفرد", "en": "Solo"},
    "audio.track.fade_in": {"ar": "تلاشي دخول (ث)", "en": "Fade in (s)"},
    "audio.track.fade_out": {"ar": "تلاشي خروج (ث)", "en": "Fade out (s)"},
    "audio.autoduck": {"ar": "خفض تلقائي للموسيقى تحت الحوار (−18 dB)", "en": "Auto-duck music under dialogue (−18 dB)"},
    "audio.autoduck.on_caption": {"ar": "مستوى الموسيقى الفعلي أثناء الحوار: {ducked} (مخفوض من {orig})", "en": "Effective music level while dialogue plays: {ducked} (ducked from {orig})"},
    "audio.autoduck.off_caption": {"ar": "الخفض التلقائي متوقف — تبقى الموسيقى عند المستوى المحدَّد حتى أثناء الحوار.", "en": "Auto-duck is off — music stays at its set volume even under dialogue."},
    "audio.lufs.title": {"ar": "مقياس LUFS — الحالي: {current} LUFS · الهدف: {target} LUFS", "en": "LUFS Meter — current: {current} LUFS · target: {target} LUFS"},
    "audio.assigned_clips": {"ar": "المقاطع المُعيَّنة", "en": "Assigned Clips"},
    "audio.btn.remove": {"ar": "إزالة", "en": "Remove"},
    "audio.demucs.title": {"ar": "🎛️ Demucs — أداة صوت مستقلة", "en": "🎛️ Demucs — Standalone Audio Tool"},
    "audio.demucs.desc": {"ar": "صوت خام → إزالة الضجيج → فصل الصوت البشري → تعديل ترددي → إخراج −14 LUFS.", "en": "Raw audio in → noise removal → vocal separation → EQ → −14 LUFS out."},
    "audio.demucs.upload": {"ar": "صوت خام", "en": "Raw audio"},
    "audio.btn.process": {"ar": "معالجة", "en": "Process"},
    "audio.demucs.stage1": {"ar": "إزالة الضجيج", "en": "Noise removal"},
    "audio.demucs.stage2": {"ar": "فصل الصوت البشري", "en": "Vocal separation"},
    "audio.demucs.stage3": {"ar": "تعديل ترددي", "en": "EQ"},
    "audio.demucs.stage4": {"ar": "التطبيع إلى −14 LUFS", "en": "Normalizing to −14 LUFS"},
    "audio.demucs.before": {"ar": "قبل", "en": "Before"},
    "audio.demucs.after": {"ar": "بعد", "en": "After"},
    "audio.demucs.download": {"ar": "⬇ تنزيل الصوت المُعالَج", "en": "⬇ Download processed audio"},

    # ---- motion generation screen (§9) ----
    "motion.subtitle": {
        "ar": "حركة WAN 2.2 وBIE — داخل لوحة خصائص المشهد. لا يوجد محرك توليد حقيقي موصول؛ هذا يحاكي التوقيت وتدفّق حارس الجودة.",
        "en": "WAN 2.2 motion + BIE — scene properties panel. No real generation backend is wired in; this simulates timing and the quality-guard flow.",
    },
    "motion.scene.label": {"ar": "المشهد", "en": "Scene"},
    "motion.scene": {"ar": "مشهد {n}", "en": "Scene {n}"},
    "motion.status.not_animated": {"ar": "لم يُحرَّك", "en": "Not Animated"},
    "motion.status.queued": {"ar": "بانتظار المعالج الرسومي", "en": "Waiting for GPU"},
    "motion.status.generating": {"ar": "جارٍ التوليد…", "en": "Generating…"},
    "motion.status.quality_check": {"ar": "حارس الجودة يفحص…", "en": "Quality Guard Checking…"},
    "motion.status.complete": {"ar": "مكتمل", "en": "Complete"},
    "motion.camera.title": {"ar": "تأثير الكاميرا", "en": "Camera Effect"},
    "motion.camera.pan": {"ar": "تحريك أفقي", "en": "Pan"},
    "motion.camera.zoom": {"ar": "تقريب", "en": "Zoom"},
    "motion.camera.dolly": {"ar": "دولي", "en": "Dolly"},
    "motion.camera.rack_focus": {"ar": "تغيير التركيز", "en": "Rack Focus"},
    "motion.body_motion": {"ar": "حركة الجسم", "en": "Body Motion"},
    "motion.body_motion.desc": {
        "ar": "تطبّق حركة جسم الشخصية فوق تأثير الكاميرا (المشي، الإيماءات، إلخ).",
        "en": "Applies subject body movement on top of the camera effect (walking, gestures, etc.).",
    },
    "motion.fx.title": {"ar": "طبقة المؤثرات السينمائية", "en": "Cinematic FX Layer"},
    "motion.fx.smoke": {"ar": "دخان", "en": "Smoke"},
    "motion.fx.haze": {"ar": "ضباب", "en": "Haze"},
    "motion.fx.explosions": {"ar": "انفجارات", "en": "Explosions"},
    "motion.auto.title": {"ar": "تلقائي (بلا تحكم من المستخدم)", "en": "Automatic (no user control)"},
    "motion.auto.era": {"ar": "🎞️ الحركة المناسبة للحقبة:", "en": "🎞️ Era-appropriate motion:"},
    "motion.auto.era_note": {"ar": "يُختار الأسلوب تلقائياً وبصمت حسب سياق المشهد.", "en": "style is chosen automatically from scene context, silently."},
    "motion.auto.bie": {"ar": "🧬 BIE:", "en": "🧬 BIE:"},
    "motion.auto.bie_note": {"ar": "يعمل في الخلفية دون أي عناصر تحكم ظاهرة للمستخدم.", "en": "runs in the background with no user-facing controls."},
    "motion.auto.applied": {"ar": "مُطبَّق ✓", "en": "Applied ✓"},
    "motion.auto.applying": {"ar": "قيد التطبيق…", "en": "Applying…"},
    "motion.auto.running": {"ar": "قيد التشغيل…", "en": "Running…"},
    "motion.auto.dash": {"ar": "—", "en": "—"},
    "motion.quality.title": {"ar": "🛡️ حارس الجودة:", "en": "🛡️ Quality Guard:"},
    "motion.quality.drift": {
        "ar": "تم اكتشاف انحراف في الإطارات 42–58 — إعادة توليد تلقائية، لا حاجة لأي إجراء.",
        "en": "Drift detected on frames 42–58 — auto re-generated, no action needed.",
    },
    "motion.quality.none": {"ar": "لم يُكتشف أي انحراف.", "en": "No drift detected."},
    "motion.quality.banner": {"ar": "🛡️ حارس الجودة: تم اكتشاف انحراف في الإطارات 42–58 — إعادة توليد الإطارات المتأثرة تلقائياً…", "en": "🛡️ Quality guard: drift detected on frames 42–58 — auto re-generating affected frames…"},
    "motion.btn.generate": {"ar": "▶ توليد الحركة", "en": "▶ Generate Motion"},
    "motion.gpu_wait": {"ar": "🖥️ بانتظار المعالج الرسومي — {n} مهمة أمامك…", "en": "🖥️ Waiting for GPU — {n} job(s) ahead…"},
    "motion.generating_text": {"ar": "جارٍ توليد الحركة — يُطبَّق أسلوب الحقبة تلقائياً…", "en": "Generating motion — era-appropriate style applied automatically…"},

    # ---- subtitles & captions screen (§10) ----
    "sub.subtitle": {
        "ar": "طبقة ترجمة مستقلة. لا يوجد نموذج Whisper/NLLB موصول — النسخ والترجمة محاكاة.",
        "en": "Independent subtitle layer. No Whisper/NLLB model is wired in here — transcription and translation are simulated.",
    },
    "sub.empty": {"ar": "لا توجد ترجمة بعد لهذا المشروع.", "en": "No subtitles yet for this project."},
    "sub.btn.auto_generate": {"ar": "🪄 توليد تلقائي من الصوت (Whisper)", "en": "🪄 Auto-generate from Audio (Whisper)"},
    "sub.transcribing": {"ar": "جارٍ تحويل الصوت إلى نص (Whisper)…", "en": "Transcribing audio (Whisper)…"},
    "sub.out_of_sync": {
        "ar": "⚠ قد تكون الترجمة غير متزامنة — تغيّر مقطع الصوت الأساسي منذ توليدها.",
        "en": "⚠ Subtitles may be out of sync — the underlying audio track changed since these were generated.",
    },
    "sub.btn.autosync": {"ar": "🔁 مزامنة تلقائية مع الصوت", "en": "🔁 Auto-sync with Audio"},
    "sub.syncing": {"ar": "جارٍ إعادة محاذاة توقيت الترجمة مع الصوت…", "en": "Re-aligning subtitle timing to audio…"},
    "sub.btn.sim_desync": {"ar": "🔧 محاكاة: تغيّر مقطع الصوت", "en": "🔧 Simulate: audio track changed"},
    "sub.sim_desync_caption": {
        "ar": "أداة محاكاة — تُحاكي إعادة تحرير الصوت لجعل تحذير عدم التزامن أعلاه قابلاً للوصول.",
        "en": "Demo control — simulates the audio being re-edited so the out-of-sync warning above becomes reachable.",
    },
    "sub.blocks.title": {"ar": "✏️ كتل الترجمة", "en": "✏️ Subtitle Blocks"},
    "sub.start_ms": {"ar": "البداية (مللي ثانية)", "en": "Start (ms)"},
    "sub.end_ms": {"ar": "النهاية (مللي ثانية)", "en": "End (ms)"},
    "sub.btn.delete": {"ar": "🗑 حذف", "en": "🗑 Delete"},
    "sub.en_line": {"ar": "الإنجليزية: {text}", "en": "EN: {text}"},
    "sub.btn.add_block": {"ar": "+ إضافة كتلة", "en": "+ Add Block"},
    "sub.shift.title": {"ar": "⏱ إزاحة التوقيت", "en": "⏱ Timing Shift"},
    "sub.shift.label": {"ar": "إزاحة كل الكتل (مللي ثانية، ± مسموح)", "en": "Shift all blocks by (ms, ± allowed)"},
    "sub.shift.preview": {"ar": "معاينة حيّة — ستنتقل الكتلة 1 إلى {start} → {end}", "en": "Live preview — Block 1 would move to {start} → {end}"},
    "sub.btn.apply_shift": {"ar": "تطبيق الإزاحة على كل الكتل", "en": "Apply Shift to All Blocks"},
    "sub.style.title": {"ar": "🎨 تنسيق الترجمة", "en": "🎨 Caption Styling"},
    "sub.style.font": {"ar": "الخط", "en": "Font"},
    "sub.style.size": {"ar": "الحجم (بكسل)", "en": "Size (px)"},
    "sub.style.color": {"ar": "لون النص", "en": "Text color"},
    "sub.style.position": {"ar": "الموضع", "en": "Position"},
    "sub.style.top": {"ar": "أعلى", "en": "Top"},
    "sub.style.bottom": {"ar": "أسفل", "en": "Bottom"},
    "sub.style.bg": {"ar": "خلفية للنص", "en": "Background box"},
    "sub.style.bg_opacity": {"ar": "شفافية الخلفية (%)", "en": "Background opacity (%)"},
    "sub.style.preview_block": {"ar": "معاينة الكتلة", "en": "Preview block"},
    "sub.style.block_n": {"ar": "كتلة {n}", "en": "Block {n}"},
    "sub.style.empty_block": {"ar": "(كتلة فارغة)", "en": "(empty block)"},
    "sub.style.note": {
        "ar": "المعاينة تعرض نصاً عربياً حقيقياً مع التشكيل — وليست معاينة لاتينية بديلة أبداً.",
        "en": "Preview renders real reshaped Arabic with diacritics — never a Latin placeholder.",
    },
    "sub.lang.title": {"ar": "🌐 لغات الترجمة", "en": "🌐 Caption Languages"},
    "sub.lang.desc": {
        "ar": "العربية والإنجليزية تشكّلان الطبقة الثنائية المطلوبة وتبقيان مفعّلتين. أضف حتى 3 لغات عبر ترجمة NLLB-200.",
        "en": "Arabic + English form the required dual-language layer and stay on. Add up to 3 more via NLLB-200 translation.",
    },
    "sub.lang.ar": {"ar": "العربية", "en": "Arabic"},
    "sub.lang.en": {"ar": "الإنجليزية", "en": "English"},
    "sub.lang.fr": {"ar": "الفرنسية", "en": "French"},
    "sub.lang.ur": {"ar": "الأردية", "en": "Urdu"},
    "sub.lang.ms": {"ar": "الملايو", "en": "Malay"},
    "sub.btn.translate": {"ar": "ترجمة", "en": "Translate"},
    "sub.translating": {"ar": "جارٍ الترجمة إلى {lang} (NLLB-200)…", "en": "Translating to {lang} (NLLB-200)…"},
    "sub.translated": {"ar": "✓ مُترجَم", "en": "✓ Translated"},
    "sub.translate_failed": {"ar": "✕ فشل", "en": "✕ Failed"},
    "sub.btn.retry": {"ar": "↻ إعادة المحاولة", "en": "↻ Retry"},
    "sub.override.title": {"ar": "🎬 تجاوز اللغة لكل مشهد (14 مشهداً)", "en": "🎬 Per-Scene Language Override (14 scenes)"},
    "sub.override.use_global": {"ar": "استخدام المسار العام", "en": "Use global track"},
    "sub.override.scene": {"ar": "مشهد {n}", "en": "Scene {n}"},
    "sub.io.title": {"ar": "📄 استيراد / تصدير SRT", "en": "📄 SRT Import / Export"},
    "sub.io.import": {"ar": "استيراد .srt", "en": "Import .srt"},
    "sub.io.import_note": {
        "ar": "الملف المستورد يحتوي على {n} كتلة موقّتة — راجعها قبل استبدال كتلك الحالية.",
        "en": "Imported file contains {n} timed block(s) — review before replacing your current blocks.",
    },
    "sub.io.export": {"ar": "⬇ تصدير الكتل الحالية كـ .srt", "en": "⬇ Export current blocks as .srt"},
    "sub.burn_in": {"ar": "دمج الترجمة داخل الفيديو عند التصدير", "en": "Burn subtitles into video at export"},
    "sub.burn_in.caption": {
        "ar": "عند التفعيل، تُدمَج الترجمة بشكل دائم في الفيديو أثناء التصدير (§11). عند الإيقاف، تبقى الترجمة مساراً مستقلاً قابلاً للإزالة.",
        "en": "When on, captions are permanently rendered into the video during Export (§11). When off, subtitles stay a separate, removable track.",
    },

    # ---- export & render screen (§11) ----
    "exp.subtitle": {
        "ar": "تصدير متعدد النسب في آن واحد. لا يوجد محرك ترميز حقيقي موصول — هذا يحاكي التوقيت وفشلاً لأحد النسب.",
        "en": "Simultaneous multi-ratio 4K export. No real encoder is wired in — this simulates timing and a per-ratio failure.",
    },
    "exp.settings.title": {"ar": "⚙️ إعدادات التصدير", "en": "⚙️ Export Settings"},
    "exp.ratios.title": {"ar": "النسب (تُصدَّر كلها في آن واحد، كل واحدة بدقة 4K كاملة)", "en": "Ratios (all export simultaneously, each at full 4K)"},
    "exp.format": {"ar": "الصيغة", "en": "Format"},
    "exp.bitrate": {"ar": "إعداد معدل البت", "en": "Bitrate preset"},
    "exp.burn_in": {"ar": "دمج الترجمة", "en": "Burn-in subtitles"},
    "exp.mixdown": {"ar": "خلط الصوت إلى ستيريو رئيسي", "en": "Mix audio down to stereo master"},
    "exp.proxy.title": {"ar": "🖼️ معاينة مصغّرة (¼ الدقة)", "en": "🖼️ Proxy Preview (¼ res)"},
    "exp.proxy.select_ratio": {"ar": "اختر نسبة واحدة على الأقل للمعاينة.", "en": "Select at least one ratio to preview."},
    "exp.disk.estimate": {"ar": "الحجم التقديري للتصدير: ~{size} جيجابايت عبر {n} نسبة · المساحة الحرة: {free} جيجابايت", "en": "Estimated export size: ~{size} GB across {n} ratio(s) · Free disk space: {free} GB"},
    "exp.disk.warning": {
        "ar": "⚠ لا توجد مساحة قرص كافية — يحتاج هذا التصدير إلى ~{size} جيجابايت لكن {free} جيجابايت فقط متاحة. أخلِ مساحة، أو قلّل عدد النسب، أو تابع على مسؤوليتك.",
        "en": "⚠ Not enough free disk space — this export needs ~{size} GB but only {free} GB is free. Free up space, reduce the number of ratios, or proceed at your own risk.",
    },
    "exp.disk.proceed_anyway": {"ar": "المتابعة رغم ذلك (قد يفشل التصدير في المنتصف)", "en": "Proceed anyway (export may fail partway through)"},
    "exp.btn.start": {"ar": "▶ بدء التصدير", "en": "▶ Start Export"},
    "exp.btn.pause": {"ar": "⏸ إيقاف الكل مؤقتاً", "en": "⏸ Pause All"},
    "exp.btn.resume": {"ar": "▶ استئناف", "en": "▶ Resume"},
    "exp.btn.open_folder": {"ar": "📂 فتح مجلد الإخراج", "en": "📂 Open Output Folder"},
    "exp.toast.opened_folder": {"ar": "تم الفتح: exports/hasaballa_project_01/", "en": "Opened: exports/hasaballa_project_01/"},
    "exp.btn.new_export": {"ar": "🔄 بدء تصدير جديد", "en": "🔄 Start New Export"},
    "exp.queue.title": {"ar": "📋 قائمة انتظار التصدير", "en": "📋 Render Queue"},
    "exp.status.not_started": {"ar": "لم يبدأ", "en": "Not Started"},
    "exp.status.queued": {"ar": "قيد الانتظار", "en": "Queued"},
    "exp.status.rendering": {"ar": "قيد الترميز…", "en": "Rendering…"},
    "exp.status.paused": {"ar": "متوقّف مؤقتاً", "en": "Paused"},
    "exp.status.complete": {"ar": "مكتمل", "en": "Complete"},
    "exp.status.failed": {"ar": "فشل", "en": "Failed"},
    "exp.failed_note": {"ar": "فشلت نسبة {ratio} أثناء الترميز — النسب الأخرى غير متأثرة وتستمر في التصدير.", "en": "{ratio} failed during encoding — the other ratios are unaffected and keep rendering."},
    "exp.btn.retry_ratio": {"ar": "↻ إعادة محاولة {ratio}", "en": "↻ Retry {ratio}"},
    "exp.bitrate.youtube": {"ar": "45 ميجابت فيديو / 384 كيلوبت صوت", "en": "45 Mbps video / 384 kbps audio"},
    "exp.bitrate.instagram": {"ar": "25 ميجابت فيديو / 256 كيلوبت صوت", "en": "25 Mbps video / 256 kbps audio"},
    "exp.bitrate.whatsapp": {"ar": "8 ميجابت فيديو / 128 كيلوبت صوت", "en": "8 Mbps video / 128 kbps audio"},

    # ---- publishing screen (§15) — the only online surface ----
    "pub.subtitle": {
        "ar": "الشاشة الوحيدة في المنصة التي تستخدم الإنترنت. لا يوجد اتصال حقيقي بـ Google OAuth أو YouTube API موصول.",
        "en": "The only screen in the platform that uses the internet. No real Google OAuth or YouTube API call is wired in.",
    },
    "pub.offline_default": {
        "ar": "📴 النشر غير متاح أثناء عدم الاتصال — هذا هو الوضع الافتراضي المتوقّع. اذهب إلى الإعدادات (§14) ← الوصول الذكي للإنترنت لتفعيل الاتصال صراحةً من أجل النشر.",
        "en": "📴 Publishing is unavailable while offline — this is the expected default state. Go to Settings (§14) → Smart Internet Access and explicitly allow internet access to publish.",
    },
    "pub.demo.go_online": {"ar": "🔧 محاكاة: تفعيل الإنترنت (يُضبط عادةً من الإعدادات §14)", "en": "🔧 Demo: simulate internet available (normally set in Settings §14)"},
    "pub.demo.go_offline": {"ar": "🔧 محاكاة: قطع الاتصال", "en": "🔧 Demo: go offline"},
    "pub.account.title": {"ar": "🔐 حساب يوتيوب", "en": "🔐 YouTube Account"},
    "pub.not_authenticated": {"ar": "لم يتم تسجيل الدخول.", "en": "Not authenticated."},
    "pub.btn.signin": {"ar": "تسجيل الدخول عبر Google", "en": "Sign in with Google"},
    "pub.authenticating": {"ar": "جارٍ المصادقة…", "en": "Authenticating…"},
    "pub.token_expired": {"ar": "انتهت صلاحية الجلسة. الرجاء تسجيل الدخول مجدداً للمتابعة في النشر.", "en": "Your session has expired. Please sign in again to continue publishing."},
    "pub.signed_in_as": {"ar": "تم تسجيل الدخول باسم {channel}", "en": "Signed in as {channel}"},
    "pub.token_secure": {"ar": "🔒 الرمز مخزَّن مشفَّراً", "en": "🔒 Token stored encrypted"},
    "pub.btn.expire_demo": {"ar": "محاكاة انتهاء صلاحية الرمز", "en": "Simulate token expiry"},
    "pub.expire_demo_caption": {
        "ar": "أداة محاكاة أعلاه — عادةً تنتهي صلاحية الرموز بصمت في الخلفية وتظهر هذه الحالة عند محاولة النشر التالية.",
        "en": "Demo control above — normally tokens expire silently in the background and this state appears on the next publish attempt.",
    },
    "pub.sign_in_prompt": {"ar": "سجّل الدخول أعلاه للرفع.", "en": "Sign in above to upload."},
    "pub.oauth.title": {"ar": "تسجيل الدخول عبر Google — الموافقة", "en": "Sign in with Google — Consent"},
    "pub.oauth.requesting": {"ar": "{channel} يطلب أذونات YouTube Data API v3 التالية:", "en": "{channel} is requesting the following YouTube Data API v3 permissions:"},
    "pub.oauth.scopes": {
        "ar": "- رفع الفيديوهات وإدارتها\n- عرض معلومات القناة الأساسية\n- عرض تحليلات القناة (AdSense/CPM)",
        "en": "- Upload and manage your videos\n- View your channel's basic info\n- View channel analytics (AdSense/CPM)",
    },
    "pub.oauth.caption": {
        "ar": "يُخزَّن الرمز مشفَّراً على هذا الجهاز — أبداً كنص عادي — ويُستخدم فقط لإجراءات النشر التي تبدأها أنت.",
        "en": "Your token is stored encrypted on this machine — never in plain text — and only used for publishing actions you initiate.",
    },
    "pub.btn.allow": {"ar": "سماح", "en": "Allow"},
    "pub.btn.deny": {"ar": "رفض", "en": "Deny"},
    "pub.upload.title": {"ar": "⬆️ الرفع إلى يوتيوب", "en": "⬆️ Upload to YouTube"},
    "pub.title.label": {"ar": "العنوان (بالعربية)", "en": "Title (Arabic)"},
    "pub.desc.label": {"ar": "الوصف (بالعربية)", "en": "Description (Arabic)"},
    "pub.tags.label": {"ar": "الوسوم (مفصولة بفواصل، بالعربية)", "en": "Tags (comma-separated, Arabic)"},
    "pub.privacy.label": {"ar": "الخصوصية", "en": "Privacy"},
    "pub.privacy.public": {"ar": "عام", "en": "Public"},
    "pub.privacy.unlisted": {"ar": "غير مدرَج", "en": "Unlisted"},
    "pub.privacy.private": {"ar": "خاص", "en": "Private"},
    "pub.thumbnail": {"ar": "الصورة المصغّرة", "en": "Thumbnail"},
    "pub.upload_failed": {"ar": "فشل الرفع — انقطع الاتصال بالإنترنت أثناء العملية.", "en": "Upload failed — network connection was interrupted partway through."},
    "pub.btn.retry_upload": {"ar": "↻ إعادة محاولة الرفع", "en": "↻ Retry Upload"},
    "pub.btn.upload": {"ar": "⬆ الرفع إلى يوتيوب", "en": "⬆ Upload to YouTube"},
    "pub.uploading": {"ar": "جارٍ الرفع…", "en": "Uploading…"},
    "pub.published": {"ar": "✅ تم النشر! {title}", "en": "✅ Published! {title}"},
    "pub.btn.publish_another": {"ar": "📤 نشر فيديو آخر", "en": "📤 Publish Another Video"},
    "pub.analytics.title": {"ar": "💰 الإيرادات والتحليلات", "en": "💰 Revenue & Analytics"},
    "pub.stat.revenue": {"ar": "الإيراد التقديري", "en": "Est. Revenue"},
    "pub.stat.cpm": {"ar": "CPM", "en": "CPM"},
    "pub.stat.views": {"ar": "المشاهدات", "en": "Views"},
    "pub.stat.watch_time": {"ar": "وقت المشاهدة", "en": "Watch Time"},
    "pub.chart.caption": {"ar": "المشاهدات — آخر 7 أيام", "en": "Views — last 7 days"},
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
