"""Native PySide6 port of publishing_app.py (§15 of the UI audit) — the
ONLY online surface in the platform. Per the UX note, the default state is
offline/unavailable and is designed first; going online is normally a
Settings (§14) action, stood in here by a clearly-labelled demo toggle so
the rest of the flow (OAuth consent → upload → publish → analytics) is
reachable in isolation. No real Google OAuth/YouTube API call is wired in.
"""

from PySide6.QtCore import QSize, Qt, QThreadPool
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from common.build_flags import DEV_BUILD
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import BarChart, Card, CaptionLabel, SectionLabel, clear_layout
from common.scenes import scene_paths
from common.workers import Worker

FAKE_CHANNEL = "Hasaballa Studio"
FAKE_VIDEO_ID = "hb-demo-0142"
PRIVACY_OPTIONS = [("public", "pub.privacy.public"), ("unlisted", "pub.privacy.unlisted"), ("private", "pub.privacy.private")]


class OAuthConsentDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(t("pub.oauth.title"))
        self.setMinimumWidth(380)
        self.allowed = False
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(t("pub.oauth.requesting", channel=FAKE_CHANNEL)))
        scopes = QLabel(t("pub.oauth.scopes"))
        scopes.setWordWrap(True)
        lay.addWidget(scopes)
        caption = CaptionLabel(t("pub.oauth.caption"))
        lay.addWidget(caption)
        row = QHBoxLayout()
        allow_btn = QPushButton(t("pub.btn.allow"))
        allow_btn.setProperty("variant", "primary")
        allow_btn.clicked.connect(self._allow)
        deny_btn = QPushButton(t("pub.btn.deny"))
        deny_btn.clicked.connect(self.reject)
        row.addWidget(allow_btn)
        row.addWidget(deny_btn)
        lay.addLayout(row)

    def _allow(self):
        self.allowed = True
        self.accept()


class PublishingScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self._workers = []
        self.scenes = scene_paths()

        self.pub_connection = "offline"
        self.auth_status = "not_authenticated"
        self.upload_status = "idle"
        self.upload_attempts = 0
        self.title_ar = "قصة من الصحراء"
        self.desc_ar = "فيلم قصير من إنتاج منصة حصبلة الذكية."
        self.tags_ar = "قصة, صحراء, تراث"
        self.privacy = "public"

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(16)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self._build_offline_notice()
        self._build_demo_row()
        self._build_account_section()
        self._build_upload_section()
        self._build_analytics_section()
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()
        self._render()

    # ------------------------------------------------------------------
    def _run_worker(self, fn, on_done):
        worker = Worker(fn)
        self._workers.append(worker)

        def settle(_result=None):
            if worker in self._workers:
                self._workers.remove(worker)
            on_done()

        worker.signals.finished.connect(settle)
        QThreadPool.globalInstance().start(worker)

    # ------------------------------------------------------------------
    def _build_offline_notice(self):
        self.offline_notice = QLabel()
        self.offline_notice.setWordWrap(True)
        self.outer.addWidget(self.offline_notice)

    def _build_demo_row(self):
        # QA-only: force the online/offline connection state without a real
        # OAuth round-trip. Absent from client builds (see common/build_flags).
        self.demo_online_btn = None
        self.demo_offline_btn = None
        if not DEV_BUILD:
            return
        row = QHBoxLayout()
        row.addStretch(1)
        self.demo_online_btn = QPushButton()
        self.demo_online_btn.clicked.connect(self._demo_go_online)
        row.addWidget(self.demo_online_btn)
        self.demo_offline_btn = QPushButton()
        self.demo_offline_btn.clicked.connect(self._demo_go_offline)
        row.addWidget(self.demo_offline_btn)
        self.outer.addLayout(row)

    def _demo_go_online(self):
        self.pub_connection = "online"
        self._render()

    def _demo_go_offline(self):
        self.pub_connection = "offline"
        self.auth_status = "not_authenticated"
        self.upload_status = "idle"
        self._render()

    # ------------------------------------------------------------------
    def _build_account_section(self):
        self.account_card = Card()
        lay = self.account_card.layout()
        self.account_title = SectionLabel()
        lay.addWidget(self.account_title)

        self.not_auth_label = QLabel()
        lay.addWidget(self.not_auth_label)
        self.signin_btn = QPushButton()
        self.signin_btn.setProperty("variant", "primary")
        self.signin_btn.clicked.connect(self._start_signin)
        lay.addWidget(self.signin_btn)

        self.token_expired_label = QLabel()
        self.token_expired_label.setWordWrap(True)
        lay.addWidget(self.token_expired_label)

        self.authenticated_row = QHBoxLayout()
        self.signed_in_label = QLabel()
        self.authenticated_row.addWidget(self.signed_in_label, 1)
        self.token_badge = CaptionLabel()
        self.authenticated_row.addWidget(self.token_badge)
        # QA-only: force the token-expired state. Absent from client builds.
        self.expire_demo_btn = None
        self.expire_demo_caption = None
        if DEV_BUILD:
            self.expire_demo_btn = QPushButton()
            self.expire_demo_btn.clicked.connect(self._expire_token)
            self.authenticated_row.addWidget(self.expire_demo_btn)
        lay.addLayout(self.authenticated_row)
        if DEV_BUILD:
            self.expire_demo_caption = CaptionLabel()
            lay.addWidget(self.expire_demo_caption)

        self.outer.addWidget(self.account_card)

    def _start_signin(self):
        dlg = OAuthConsentDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.allowed:
            self.auth_status = "authenticating"
            self._render()
            self._run_worker(lambda: __import__("time").sleep(0.6), self._finish_signin)

    def _finish_signin(self):
        self.auth_status = "authenticated"
        self._render()

    def _expire_token(self):
        self.auth_status = "token_expired"
        self._render()

    # ------------------------------------------------------------------
    def _build_upload_section(self):
        self.upload_title = SectionLabel()
        self.outer.addWidget(self.upload_title)

        self.sign_in_prompt = QLabel()
        self.outer.addWidget(self.sign_in_prompt)

        self.upload_form = QWidget()
        form_row = QHBoxLayout(self.upload_form)
        left = QVBoxLayout()
        self.title_label = QLabel()
        left.addWidget(self.title_label)
        self.title_edit = QLineEdit(self.title_ar)
        self.title_edit.setLayoutDirection(Qt.RightToLeft)
        self.title_edit.textChanged.connect(lambda text: setattr(self, "title_ar", text))
        left.addWidget(self.title_edit)

        self.desc_label = QLabel()
        left.addWidget(self.desc_label)
        self.desc_edit = QTextEdit()
        self.desc_edit.setPlainText(self.desc_ar)
        self.desc_edit.setFixedHeight(70)
        self.desc_edit.setLayoutDirection(Qt.RightToLeft)
        self.desc_edit.textChanged.connect(lambda: setattr(self, "desc_ar", self.desc_edit.toPlainText()))
        left.addWidget(self.desc_edit)

        self.tags_label = QLabel()
        left.addWidget(self.tags_label)
        self.tags_edit = QLineEdit(self.tags_ar)
        self.tags_edit.setLayoutDirection(Qt.RightToLeft)
        self.tags_edit.textChanged.connect(lambda text: setattr(self, "tags_ar", text))
        left.addWidget(self.tags_edit)

        self.privacy_label = QLabel()
        left.addWidget(self.privacy_label)
        self.privacy_combo = QComboBox()
        self.privacy_combo.currentIndexChanged.connect(self._on_privacy_changed)
        left.addWidget(self.privacy_combo)
        form_row.addLayout(left, 2)

        right = QVBoxLayout()
        self.thumbnail_label = QLabel()
        thumb = QLabel()
        thumb.setFixedSize(QSize(160, 90))
        from PySide6.QtGui import QPixmap

        pix = QPixmap(str(self.scenes[0])).scaled(thumb.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        thumb.setPixmap(pix)
        thumb.setStyleSheet("border-radius:10px;")
        right.addWidget(self.thumbnail_label)
        right.addWidget(thumb)
        form_row.addLayout(right, 1)
        self.outer.addWidget(self.upload_form)

        self.upload_failed_label = QLabel()
        self.upload_failed_label.setWordWrap(True)
        self.upload_failed_label.setVisible(False)
        self.outer.addWidget(self.upload_failed_label)

        btn_row = QHBoxLayout()
        self.upload_btn = QPushButton()
        self.upload_btn.setProperty("variant", "primary")
        self.upload_btn.clicked.connect(self._start_upload)
        btn_row.addWidget(self.upload_btn)
        self.retry_upload_btn = QPushButton()
        self.retry_upload_btn.setProperty("variant", "primary")
        self.retry_upload_btn.clicked.connect(self._start_upload)
        self.retry_upload_btn.setVisible(False)
        btn_row.addWidget(self.retry_upload_btn)
        self.outer.addLayout(btn_row)

        self.published_card = Card()
        pub_lay = self.published_card.layout()
        self.published_label = QLabel()
        self.published_label.setWordWrap(True)
        pub_lay.addWidget(self.published_label)
        self.video_link_label = QLabel()
        pub_lay.addWidget(self.video_link_label)
        self.publish_another_btn = QPushButton()
        self.publish_another_btn.clicked.connect(self._publish_another)
        pub_lay.addWidget(self.publish_another_btn)
        self.outer.addWidget(self.published_card)

    def _on_privacy_changed(self, index: int):
        self.privacy = PRIVACY_OPTIONS[index][0]

    def _start_upload(self):
        self.upload_btn.setEnabled(False)
        self.retry_upload_btn.setEnabled(False)
        self._run_worker(self._simulate_upload, self._finish_upload)

    @staticmethod
    def _simulate_upload():
        import time

        time.sleep(0.9)

    def _finish_upload(self):
        if self.upload_attempts == 0:
            self.upload_status = "failed"
        else:
            self.upload_status = "published"
        self.upload_attempts += 1
        self._render()

    def _publish_another(self):
        self.upload_status = "idle"
        self.upload_attempts = 0
        self._render()

    # ------------------------------------------------------------------
    def _build_analytics_section(self):
        self.analytics_title = SectionLabel()
        self.outer.addWidget(self.analytics_title)
        stat_row = QHBoxLayout()
        self._stat_labels = {}
        for key in ("pub.stat.revenue", "pub.stat.cpm", "pub.stat.views", "pub.stat.watch_time"):
            card = Card(flat=True, margins=(10, 10, 10, 10), spacing=2)
            lay = card.layout()
            val_label = QLabel()
            val_label.setStyleSheet("font-size:18px; font-weight:800;")
            val_label.setAlignment(Qt.AlignCenter)
            lay.addWidget(val_label)
            lbl_label = QLabel()
            lbl_label.setAlignment(Qt.AlignCenter)
            lay.addWidget(lbl_label)
            stat_row.addWidget(card)
            self._stat_labels[key] = (val_label, lbl_label)
        self.outer.addLayout(stat_row)

        self.chart_caption = CaptionLabel()
        self.outer.addWidget(self.chart_caption)
        self.views_chart = BarChart([820, 1140, 990, 1560, 2010, 2430, 3530], color="#2F6FEF")
        self.outer.addWidget(self.views_chart)

    STAT_VALUES = {
        "pub.stat.revenue": "$142.30", "pub.stat.cpm": "$3.85",
        "pub.stat.views": "12,480", "pub.stat.watch_time": "612 hrs",
    }

    def _render_stats(self):
        for key, (val_label, lbl_label) in self._stat_labels.items():
            val_label.setText(self.STAT_VALUES[key])
            lbl_label.setText(t(key))

    # ------------------------------------------------------------------
    def _render(self):
        online = self.pub_connection == "online"
        self.offline_notice.setVisible(not online)
        if DEV_BUILD:
            self.demo_online_btn.setVisible(not online)
            self.demo_offline_btn.setVisible(online)

        self.account_card.setVisible(online)
        self.upload_title.setVisible(online)

        if not online:
            for w in (self.sign_in_prompt, self.upload_form, self.upload_btn, self.retry_upload_btn,
                      self.published_card, self.analytics_title, self.chart_caption, self.views_chart,
                      self.upload_failed_label):
                w.setVisible(False)
            return

        status = self.auth_status
        self.not_auth_label.setVisible(status == "not_authenticated")
        self.signin_btn.setVisible(status in ("not_authenticated", "token_expired"))
        self.token_expired_label.setVisible(status == "token_expired")
        authenticated = status == "authenticated"
        self.authenticated_row.itemAt(0).widget().setVisible(authenticated)
        self.token_badge.setVisible(authenticated)
        if DEV_BUILD:
            self.expire_demo_btn.setVisible(authenticated)
            self.expire_demo_caption.setVisible(authenticated)
        if authenticated:
            self.signed_in_label.setText(t("pub.signed_in_as", channel=FAKE_CHANNEL))

        self.sign_in_prompt.setVisible(not authenticated)

        show_upload_area = authenticated
        self.upload_form.setVisible(show_upload_area and self.upload_status != "published")
        self.published_card.setVisible(self.upload_status == "published")
        self.analytics_title.setVisible(self.upload_status == "published")
        self.chart_caption.setVisible(self.upload_status == "published")
        self.views_chart.setVisible(self.upload_status == "published")

        is_failed = self.upload_status == "failed"
        self.upload_failed_label.setVisible(show_upload_area and is_failed)
        self.upload_btn.setVisible(show_upload_area and self.upload_status in ("idle",))
        self.retry_upload_btn.setVisible(show_upload_area and is_failed)
        self.upload_btn.setEnabled(True)
        self.retry_upload_btn.setEnabled(True)

        if self.upload_status == "published":
            self.published_label.setText(t("pub.published", title=self.title_ar))
            self.video_link_label.setText(f"https://youtube.com/watch?v={FAKE_VIDEO_ID}")
            self._render_stats()

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("pub.subtitle"))
        self.offline_notice.setText(t("pub.offline_default"))
        if DEV_BUILD:
            self.demo_online_btn.setText(t("pub.demo.go_online"))
            self.demo_offline_btn.setText(t("pub.demo.go_offline"))

        self.account_title.setText(t("pub.account.title"))
        self.not_auth_label.setText(t("pub.not_authenticated"))
        self.signin_btn.setText(t("pub.btn.signin"))
        self.token_expired_label.setText(t("pub.token_expired"))
        self.token_badge.setText(t("pub.token_secure"))
        if DEV_BUILD:
            self.expire_demo_btn.setText(t("pub.btn.expire_demo"))
            self.expire_demo_caption.setText(t("pub.expire_demo_caption"))
        self.sign_in_prompt.setText(t("pub.sign_in_prompt"))

        self.upload_title.setText(t("pub.upload.title"))
        self.title_label.setText(t("pub.title.label"))
        self.desc_label.setText(t("pub.desc.label"))
        self.tags_label.setText(t("pub.tags.label"))
        self.privacy_label.setText(t("pub.privacy.label"))
        idx = max(0, self.privacy_combo.currentIndex())
        self.privacy_combo.blockSignals(True)
        self.privacy_combo.clear()
        self.privacy_combo.addItems([t(k) for _c, k in PRIVACY_OPTIONS])
        self.privacy_combo.setCurrentIndex(idx)
        self.privacy_combo.blockSignals(False)
        self.thumbnail_label.setText(t("pub.thumbnail"))
        self.upload_failed_label.setText(t("pub.upload_failed"))
        self.upload_btn.setText(t("pub.btn.upload"))
        self.retry_upload_btn.setText(t("pub.btn.retry_upload"))
        self.publish_another_btn.setText(t("pub.btn.publish_another"))

        self.analytics_title.setText(t("pub.analytics.title"))
        self.chart_caption.setText(t("pub.chart.caption"))
        self._render_stats()
        self._render()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
