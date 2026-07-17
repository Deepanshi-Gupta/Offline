"""Native PySide6 port of hasaballa_gpt_chat_app.py (§1 of the UI audit) —
Hasaballa GPT chat / main window: RTL scenario input with a live char
counter, mic recording, removable reference image/audio attachments, an
aspect-ratio selector, Manual/Auto generate (run on a worker thread), and
the tool shortcut sidebar.

Task 4 additions:
* Smart Internet Access + Disconnect controls surfaced directly in the chat
  window (a thin view over the shared common/connection.py singleton, so it
  stays in sync with the header toggle and the Settings panel).
* Expand/collapse control on the scenario input box.
* Saved Projects as an in-chat slide-out drawer (client-confirmed) instead
  of a modal dialog.
* Character-pack constraints surfaced from the upload buttons, with a link
  out to the Character Pack Manager (via an injected navigator callback).
"""

from PySide6.QtCore import QByteArray, QEasingCurve, QPoint, QPropertyAnimation, QSize, Qt, QThreadPool
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.connection import ConnectionState, connection_manager
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import AudioPlayer, Card, CaptionLabel, OfflinePill, clear_layout, show_toast
from common.workers import Worker

MAX_CHARS = 15000
RATIOS = ["1:1", "9:16", "16:9"]
INPUT_HEIGHT_COMPACT = 110
INPUT_HEIGHT_EXPANDED = 340
DRAWER_WIDTH = 320
SIDEBAR_LINKS = [
    ("chat.sidebar.image_generation", "", "image_generation"),
    ("chat.sidebar.voice_cloning", "", "voice_cloning"),
    ("chat.sidebar.audio_enhance", "", "audio_layering"),
    ("chat.sidebar.audio_generate", "", "voice_cloning"),
    ("chat.sidebar.lip_sync", "", "lip_sync"),
    ("chat.sidebar.inpainting", "", None),
    ("chat.sidebar.timeline", "", None),
]
SAVED_PROJECTS_DEMO = [
    {"name": "مقهى الصباح (Morning Cafe)", "date": "2026-07-08", "ratio": "16:9"},
    {"name": "قصة الصياد (The Fisherman)", "date": "2026-07-05", "ratio": "9:16"},
]


class ChatScreen(QWidget):
    def __init__(self, parent=None, on_navigate=None):
        super().__init__(parent)
        self._dark = False
        self._on_navigate = on_navigate  # set_navigator() lets the shell inject real nav
        self.recording = False
        self.mic_unavailable_sim = False
        self.mic_error = False
        self.ref_image_bytes = None
        self.ref_audio_bytes = None
        self.aspect_ratio = "16:9"
        self.messages = []
        self.saved_projects = [dict(p) for p in SAVED_PROJECTS_DEMO]
        self._input_expanded = False
        self._player = AudioPlayer(self)
        self._workers = []

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_main(), 3)
        root.addWidget(self._build_sidebar(), 1)

        self._build_drawer()

        lang_manager.changed.connect(self._on_language_changed)
        connection_manager.changed.connect(self._render_connection)
        self.retranslate()
        self._render_messages()
        self._render_char_counter()
        self._render_recording()
        self._render_ratio_buttons()
        self._render_connection()

    # ------------------------------------------------------------------
    def _build_main(self) -> QWidget:
        card = Card(margins=(18, 16, 18, 16), spacing=10)
        lay = card.layout()

        header = QHBoxLayout()
        self.folder_btn = QPushButton("")
        self.folder_btn.setFixedSize(38, 38)
        self.folder_btn.setCursor(Qt.PointingHandCursor)
        self.folder_btn.clicked.connect(self._toggle_saved_projects)
        self.title_label = QLabel("Hasaballa GPT")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setProperty("role", "pageTitle")
        header.addWidget(self.folder_btn)
        header.addWidget(self.title_label, 1)
        header.addSpacing(38)
        lay.addLayout(header)

        # ---- connection controls (Task 4.1) — a view over connection_manager ----
        conn_row = QHBoxLayout()
        self.conn_pill = OfflinePill(dark=self._dark)
        self.conn_enable_btn = QPushButton()
        self.conn_enable_btn.setProperty("variant", "primary")
        self.conn_enable_btn.setCursor(Qt.PointingHandCursor)
        self.conn_enable_btn.clicked.connect(connection_manager.go_online)
        self.conn_disconnect_btn = QPushButton()
        self.conn_disconnect_btn.setProperty("variant", "danger")
        self.conn_disconnect_btn.setCursor(Qt.PointingHandCursor)
        self.conn_disconnect_btn.clicked.connect(connection_manager.disconnect)
        conn_row.addWidget(self.conn_pill)
        conn_row.addStretch(1)
        conn_row.addWidget(self.conn_enable_btn)
        conn_row.addWidget(self.conn_disconnect_btn)
        lay.addLayout(conn_row)

        self.msg_area = QScrollArea()
        self.msg_area.setWidgetResizable(True)
        self.msg_area.setFixedHeight(180)
        self._msg_body = QWidget()
        self._msg_lay = QVBoxLayout(self._msg_body)
        self._msg_lay.setAlignment(Qt.AlignTop)
        self.msg_area.setWidget(self._msg_body)
        lay.addWidget(self.msg_area)

        mic_row = QHBoxLayout()
        self.mic_btn = QPushButton("")
        self.mic_btn.setFixedSize(36, 36)
        self.mic_btn.setCursor(Qt.PointingHandCursor)
        self.mic_btn.clicked.connect(self._on_mic_clicked)
        mic_row.addWidget(self.mic_btn)
        self.recording_banner = QLabel()
        mic_row.addWidget(self.recording_banner, 1)
        lay.addLayout(mic_row)

        self.script_edit = QTextEdit()
        self.script_edit.setFixedHeight(INPUT_HEIGHT_COMPACT)
        self.script_edit.textChanged.connect(self._on_script_changed)
        lay.addWidget(self.script_edit)

        # char counter + expand/collapse control (Task 4.2)
        counter_row = QHBoxLayout()
        self.char_counter = QLabel()
        counter_row.addWidget(self.char_counter, 1)
        self.expand_btn = QPushButton()
        self.expand_btn.setCursor(Qt.PointingHandCursor)
        self.expand_btn.clicked.connect(self._toggle_input_expanded)
        counter_row.addWidget(self.expand_btn, 0)
        lay.addLayout(counter_row)

        attach_row = QHBoxLayout()
        self.attach_image_btn = QPushButton()
        self.attach_image_btn.clicked.connect(self._pick_image)
        self.attach_audio_btn = QPushButton()
        self.attach_audio_btn.clicked.connect(self._pick_audio)
        attach_row.addWidget(self.attach_image_btn)
        attach_row.addWidget(self.attach_audio_btn)
        attach_row.addStretch(1)
        lay.addLayout(attach_row)

        self.attachments_row = QHBoxLayout()
        lay.addLayout(self.attachments_row)

        # character-pack constraints surfaced from the upload buttons (Task 4.4)
        self.charpack_note = CaptionLabel()
        lay.addWidget(self.charpack_note)
        self.charpack_btn = QPushButton()
        self.charpack_btn.setCursor(Qt.PointingHandCursor)
        self.charpack_btn.clicked.connect(self._open_character_packs)
        lay.addWidget(self.charpack_btn, 0, Qt.AlignLeft)

        ratio_row = QHBoxLayout()
        self._ratio_buttons = {}
        for ratio in RATIOS:
            btn = QPushButton(ratio)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, r=ratio: self._set_ratio(r))
            ratio_row.addWidget(btn)
            self._ratio_buttons[ratio] = btn
        ratio_row.addStretch(2)
        lay.addLayout(ratio_row)

        gen_row = QHBoxLayout()
        self.manual_btn = QPushButton()
        self.manual_btn.setCursor(Qt.PointingHandCursor)
        self.manual_btn.clicked.connect(lambda: self._generate("chat.mode.manual"))
        self.auto_btn = QPushButton()
        self.auto_btn.setProperty("variant", "primary")
        self.auto_btn.setCursor(Qt.PointingHandCursor)
        self.auto_btn.clicked.connect(lambda: self._generate("chat.mode.auto"))
        gen_row.addWidget(self.manual_btn)
        gen_row.addWidget(self.auto_btn)
        lay.addLayout(gen_row)

        return card

    def _build_sidebar(self) -> QWidget:
        card = Card()
        card.setFixedWidth(230)
        lay = card.layout()
        self._sidebar_buttons = []
        for key, icon, target in SIDEBAR_LINKS:
            btn = QPushButton()
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c=False, k=key, tg=target: self._sidebar_clicked(k, tg))
            lay.addWidget(btn)
            self._sidebar_buttons.append((key, btn))
        lay.addStretch(1)
        return card

    # ------------------------------------------------------------------
    # connection controls (Task 4.1)
    # ------------------------------------------------------------------
    def _render_connection(self):
        state = connection_manager.state
        connecting = connection_manager.connecting
        if connecting:
            tone, text_key = "info", "app.connecting_pill"
        elif state == ConnectionState.CLOUD:
            tone, text_key = "info", "app.cloud_pill"
        elif state == ConnectionState.ONLINE:
            tone, text_key = "warning", "app.online_pill"
        else:
            tone, text_key = "success", "app.offline_pill"
        self.conn_pill.set_tone(tone)
        self.conn_pill.set_text(t(text_key))

        local = state == ConnectionState.LOCAL and not connecting
        self.conn_enable_btn.setVisible(local)
        self.conn_disconnect_btn.setVisible(not local)

    # ------------------------------------------------------------------
    # mic / recording
    # ------------------------------------------------------------------
    def _on_mic_clicked(self):
        if self.recording:
            suffix = t("chat.mic_transcribed_suffix")
            text = (self.script_edit.toPlainText() + suffix)[:MAX_CHARS]
            self.script_edit.blockSignals(True)
            self.script_edit.setPlainText(text)
            self.script_edit.blockSignals(False)
            self._render_char_counter()
            self.recording = False
        elif self.mic_unavailable_sim:
            self.mic_error = True
        else:
            self.recording = True
            self.mic_error = False
        self._render_recording()

    def _render_recording(self):
        self.mic_btn.setText("⏹" if self.recording else "")
        s = semantic(self._dark)
        if self.mic_error:
            self.recording_banner.setText(t("chat.mic_error"))
            self.recording_banner.setStyleSheet(f"color:{s['danger_fg_strong']}; font-weight:600;")
        elif self.recording:
            self.recording_banner.setText(f"{t('chat.mic_recording')}")
            self.recording_banner.setStyleSheet(f"color:{s['danger_fg_strong']}; font-weight:700;")
        else:
            self.recording_banner.setText("")
            self.recording_banner.setStyleSheet("")

    # ------------------------------------------------------------------
    # scenario text / char counter / expand
    # ------------------------------------------------------------------
    def _on_script_changed(self):
        text = self.script_edit.toPlainText()
        if len(text) > MAX_CHARS:
            trimmed = text[:MAX_CHARS]
            self.script_edit.blockSignals(True)
            self.script_edit.setPlainText(trimmed)
            cursor = self.script_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.script_edit.setTextCursor(cursor)
            self.script_edit.blockSignals(False)
        self._render_char_counter()

    def _render_char_counter(self):
        n = len(self.script_edit.toPlainText())
        s = semantic(self._dark)
        color = s["ink_fainter"]
        if n > 14500:
            color = s["danger_fg_strong"]
        elif n > 12000:
            color = s["warning_fg_strong"]
        self.char_counter.setStyleSheet(f"color:{color}; font-size:11px; font-weight:700;")
        # leading-edge alignment that follows the UI direction (RTL → right)
        self.char_counter.setAlignment(
            (Qt.AlignRight if lang_manager.is_rtl() else Qt.AlignLeft) | Qt.AlignVCenter
        )
        self.char_counter.setText(t("chat.char_counter", n=f"{n:,}", max=f"{MAX_CHARS:,}"))

    def _toggle_input_expanded(self):
        self._input_expanded = not self._input_expanded
        self.script_edit.setFixedHeight(INPUT_HEIGHT_EXPANDED if self._input_expanded else INPUT_HEIGHT_COMPACT)
        self.expand_btn.setText(t("chat.input.collapse" if self._input_expanded else "chat.input.expand"))

    # ------------------------------------------------------------------
    # attachments
    # ------------------------------------------------------------------
    def _pick_image(self):
        path, _filter = QFileDialog.getOpenFileName(self, t("chat.attach.image"), "", "Images (*.png *.jpg *.jpeg)")
        if path:
            with open(path, "rb") as f:
                self.ref_image_bytes = f.read()
            self._render_attachments()

    def _pick_audio(self):
        path, _filter = QFileDialog.getOpenFileName(self, t("chat.attach.audio"), "", "Audio (*.wav *.mp3)")
        if path:
            with open(path, "rb") as f:
                self.ref_audio_bytes = f.read()
            self._render_attachments()

    def _render_attachments(self):
        clear_layout(self.attachments_row)

        if self.ref_image_bytes:
            chip = QWidget()
            chip_lay = QHBoxLayout(chip)
            chip_lay.setContentsMargins(0, 0, 0, 0)
            pix = QPixmap()
            pix.loadFromData(QByteArray(self.ref_image_bytes))
            thumb = QLabel()
            thumb.setPixmap(pix.scaled(QSize(64, 64), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            remove_btn = QPushButton("✕")
            remove_btn.setFixedSize(24, 24)
            remove_btn.setToolTip(t("chat.remove_tooltip"))
            remove_btn.clicked.connect(self._remove_image)
            chip_lay.addWidget(thumb)
            chip_lay.addWidget(remove_btn)
            self.attachments_row.addWidget(chip)

        if self.ref_audio_bytes:
            chip = QWidget()
            chip_lay = QHBoxLayout(chip)
            chip_lay.setContentsMargins(0, 0, 0, 0)
            play_btn = QPushButton("▶")
            play_btn.setFixedSize(28, 28)
            play_btn.setToolTip(t("chat.play_tooltip"))
            play_btn.clicked.connect(lambda: self._player.play_bytes(self.ref_audio_bytes))
            remove_btn = QPushButton("✕")
            remove_btn.setFixedSize(24, 24)
            remove_btn.setToolTip(t("chat.remove_tooltip"))
            remove_btn.clicked.connect(self._remove_audio)
            chip_lay.addWidget(play_btn)
            chip_lay.addWidget(remove_btn)
            self.attachments_row.addWidget(chip)

        self.attachments_row.addStretch(1)

    def _remove_image(self):
        self.ref_image_bytes = None
        self._render_attachments()

    def _remove_audio(self):
        self.ref_audio_bytes = None
        self._render_attachments()

    def _open_character_packs(self):
        # Task 4.4: link out to the full character-pack workflow. Falls back to
        # a toast if no navigator was injected (e.g. screen shown standalone).
        if self._on_navigate:
            self._on_navigate("character_packs")
        else:
            show_toast(self, t("chat.charpack.open"), dark=self._dark)

    # ------------------------------------------------------------------
    # aspect ratio
    # ------------------------------------------------------------------
    def _set_ratio(self, ratio: str):
        self.aspect_ratio = ratio
        self._render_ratio_buttons()

    def _render_ratio_buttons(self):
        for ratio, btn in self._ratio_buttons.items():
            btn.setProperty("variant", "primary" if ratio == self.aspect_ratio else "")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    # ------------------------------------------------------------------
    # generate (worker thread — never blocks the GUI thread)
    # ------------------------------------------------------------------
    def _generate(self, mode_key: str):
        text = self.script_edit.toPlainText()
        if not text.strip():
            show_toast(self, t("chat.warn.no_scenario"), dark=self._dark)
            return
        self.manual_btn.setEnabled(False)
        self.auto_btn.setEnabled(False)
        n = len(text)
        ratio = self.aspect_ratio

        worker = Worker(self._simulate_generate)
        self._workers.append(worker)

        def done(_result=None):
            if worker in self._workers:
                self._workers.remove(worker)
            self.manual_btn.setEnabled(True)
            self.auto_btn.setEnabled(True)
            self.messages.append(t("chat.result_msg", n=f"{n:,}", ratio=ratio, mode=t(mode_key)))
            self._render_messages()

        worker.signals.finished.connect(done)
        QThreadPool.globalInstance().start(worker)

    @staticmethod
    def _simulate_generate():
        import time

        time.sleep(1.0)  # placeholder for the real generation call — off the GUI thread
        return None

    def _render_messages(self):
        clear_layout(self._msg_lay)
        if not self.messages:
            empty = QLabel(t("chat.msg_empty"))
            empty.setAlignment(Qt.AlignCenter)
            empty.setWordWrap(True)
            self._msg_lay.addWidget(empty)
            return
        s = semantic(self._dark)
        for msg in self.messages:
            bubble = QLabel(msg)
            bubble.setWordWrap(True)
            bubble.setStyleSheet(
                f"background:{s['info_bg']}; color:{s['info_fg']}; border-radius:10px; padding:8px 10px;"
            )
            self._msg_lay.addWidget(bubble)

    # ------------------------------------------------------------------
    # saved projects — in-chat slide-out drawer (Task 4.3, client-confirmed)
    # ------------------------------------------------------------------
    def _build_drawer(self):
        self.drawer = QFrame(self)
        self.drawer.setObjectName("savedDrawer")
        self.drawer.setAutoFillBackground(True)
        dlay = QVBoxLayout(self.drawer)
        dlay.setContentsMargins(14, 14, 14, 14)
        dlay.setSpacing(10)

        head = QHBoxLayout()
        self.drawer_title = QLabel()
        self.drawer_title.setProperty("role", "sectionLabel")
        self.drawer_close_btn = QPushButton("✕")
        self.drawer_close_btn.setFixedSize(28, 28)
        self.drawer_close_btn.setCursor(Qt.PointingHandCursor)
        self.drawer_close_btn.clicked.connect(self._close_drawer)
        head.addWidget(self.drawer_title, 1)
        head.addWidget(self.drawer_close_btn)
        dlay.addLayout(head)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        self._drawer_list = QVBoxLayout(body)
        self._drawer_list.setAlignment(Qt.AlignTop)
        self._drawer_list.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(body)
        dlay.addWidget(scroll, 1)

        self._drawer_open = False
        self._drawer_anim = QPropertyAnimation(self.drawer, b"pos", self)
        self._drawer_anim.setDuration(220)
        self._drawer_anim.setEasingCurve(QEasingCurve.OutCubic)
        # connected once: the handler hides the drawer only when it settled in
        # the closed state, so an open animation's finish is a no-op
        self._drawer_anim.finished.connect(self._hide_drawer_if_closed)
        self._style_drawer()
        self.drawer.hide()

    def _style_drawer(self):
        s = semantic(self._dark)
        self.drawer.setStyleSheet(
            f"#savedDrawer {{ background:{s['surface']}; border-left:1px solid {s['border']};"
            f" border-right:1px solid {s['border']}; }}"
        )

    def _drawer_width(self) -> int:
        return min(DRAWER_WIDTH, max(240, self.width() - 40))

    def _drawer_closed_pos(self, w: int) -> QPoint:
        # slide in from the trailing edge (left in RTL, right in LTR)
        return QPoint(-w if lang_manager.is_rtl() else self.width(), 0)

    def _drawer_open_pos(self, w: int) -> QPoint:
        return QPoint(0 if lang_manager.is_rtl() else self.width() - w, 0)

    def _toggle_saved_projects(self):
        if self._drawer_open:
            self._close_drawer()
        else:
            self._open_drawer()

    def _open_drawer(self):
        self._render_drawer()
        w = self._drawer_width()
        self.drawer.resize(w, self.height())
        closed, opened = self._drawer_closed_pos(w), self._drawer_open_pos(w)
        self.drawer.move(closed)
        self.drawer.show()
        self.drawer.raise_()
        self._drawer_open = True
        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(closed)
        self._drawer_anim.setEndValue(opened)
        self._drawer_anim.start()

    def _close_drawer(self):
        if not self._drawer_open:
            return
        w = self.drawer.width()
        self._drawer_open = False
        self._drawer_anim.stop()
        self._drawer_anim.setStartValue(self.drawer.pos())
        self._drawer_anim.setEndValue(self._drawer_closed_pos(w))
        self._drawer_anim.start()

    def _hide_drawer_if_closed(self):
        if not self._drawer_open:
            self.drawer.hide()

    def _render_drawer(self):
        clear_layout(self._drawer_list)
        if not self.saved_projects:
            self._drawer_list.addWidget(QLabel(t("chat.saved_projects.empty")))
            return
        for i, proj in enumerate(list(self.saved_projects)):
            row_card = Card(flat=True, margins=(10, 8, 10, 8), spacing=2)
            row_lay = row_card.layout()
            head = QHBoxLayout()
            name = QLabel(proj["name"])
            name.setStyleSheet("font-weight:700;")
            head.addWidget(name, 1)
            row_lay.addLayout(head)
            row_lay.addWidget(CaptionLabel(f"{proj['date']} · {proj['ratio']}"))
            btns = QHBoxLayout()
            open_btn = QPushButton(t("chat.saved_projects.open"))
            open_btn.clicked.connect(lambda _c=False, p=proj: self._open_project(p))
            del_btn = QPushButton(t("chat.saved_projects.delete"))
            del_btn.setProperty("variant", "danger")
            del_btn.clicked.connect(lambda _c=False, idx=i: self._delete_project(idx))
            btns.addWidget(open_btn)
            btns.addWidget(del_btn)
            btns.addStretch(1)
            row_lay.addLayout(btns)
            self._drawer_list.addWidget(row_card)

    def _open_project(self, proj: dict):
        show_toast(self, t("chat.saved_projects.would_open", name=proj["name"]), dark=self._dark)

    def _delete_project(self, idx: int):
        self.saved_projects.pop(idx)
        self._render_drawer()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_drawer_open", False):
            w = self._drawer_width()
            self.drawer.resize(w, self.height())
            self.drawer.move(self._drawer_open_pos(w))

    # ------------------------------------------------------------------
    # sidebar
    # ------------------------------------------------------------------
    def _sidebar_clicked(self, key: str, target):
        label = t(key)
        if target and self._on_navigate:
            self._on_navigate(target)
        elif target:
            show_toast(self, t("chat.sidebar.would_open", label=label), dark=self._dark)
        else:
            show_toast(self, t("chat.sidebar.not_built", label=label), dark=self._dark)

    # ------------------------------------------------------------------
    def set_navigator(self, on_navigate):
        """Injected by the app shell so in-chat links (Character Pack Manager,
        the tool sidebar) can navigate to real screens instead of toasting."""
        self._on_navigate = on_navigate

    def retranslate(self):
        self.folder_btn.setToolTip(t("chat.folder_tooltip"))
        self.conn_enable_btn.setText(t("chat.conn.enable"))
        self.conn_disconnect_btn.setText(t("chat.conn.disconnect"))
        self.script_edit.setPlaceholderText(t("chat.script_placeholder"))
        self.expand_btn.setText(t("chat.input.collapse" if self._input_expanded else "chat.input.expand"))
        self.attach_image_btn.setText(t("chat.attach.image"))
        self.attach_audio_btn.setText(t("chat.attach.audio"))
        self.charpack_note.setText(t("chat.charpack.note"))
        self.charpack_btn.setText(t("chat.charpack.open"))
        self.manual_btn.setText(t("chat.btn.manual"))
        self.auto_btn.setText(t("chat.btn.auto"))
        self.drawer_title.setText(t("chat.saved_projects.title"))
        self.drawer_close_btn.setToolTip(t("chat.saved_projects.close"))
        for key, btn in self._sidebar_buttons:
            icon = next(icon for k, icon, _tg in SIDEBAR_LINKS if k == key)
            btn.setText(f"{icon}  {t(key)}")
        self._render_recording()
        self._render_char_counter()
        self._render_messages()
        self._render_connection()
        if self._drawer_open:
            self._render_drawer()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self.conn_pill.set_dark(dark)
        self._style_drawer()
        self._render_recording()
        self._render_char_counter()
        self._render_messages()
        self._render_connection()
