"""Native PySide6 port of §13 (Import & Media).

Standard-pattern screen: a real drag-and-drop zone (QWidget dnd events), a
QFileDialog browse fallback, and a media bin. ffprobe codec detection is
simulated from the file extension. Per the audit's one UX requirement, a
codec/format error says *what* is wrong and *what to do* — never just
"failed".
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout, show_toast

CODEC_BY_EXT = {
    "mp4": "H.264", "mov": "H.264", "png": "PNG",
    "jpg": "JPEG", "jpeg": "JPEG", "wav": "PCM", "mp3": "MP3",
}
KIND_KEY_BY_EXT = {
    "mp4": "imp.kind.video", "mov": "imp.kind.video",
    "png": "imp.kind.image", "jpg": "imp.kind.image", "jpeg": "imp.kind.image",
    "wav": "imp.kind.audio", "mp3": "imp.kind.audio",
}
SUPPORTED = set(CODEC_BY_EXT)
TICK_MS = 160


class DropZone(QFrame):
    """Dashed drop target that highlights while a drag hovers over it."""

    def __init__(self, on_files, parent=None):
        super().__init__(parent)
        self._on_files = on_files
        self._dark = False
        self._hover = False
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        self.prompt = QLabel()
        self.prompt.setAlignment(Qt.AlignCenter)
        self.or_label = QLabel()
        self.or_label.setAlignment(Qt.AlignCenter)
        self.browse_btn = QPushButton()
        self.browse_btn.setProperty("variant", "primary")
        self.browse_btn.setCursor(Qt.PointingHandCursor)
        browse_row = QHBoxLayout()
        browse_row.addStretch(1)
        browse_row.addWidget(self.browse_btn)
        browse_row.addStretch(1)
        lay.addWidget(self.prompt)
        lay.addWidget(self.or_label)
        lay.addLayout(browse_row)
        self._apply_style()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._hover = True
            self._apply_style()

    def dragLeaveEvent(self, _event):
        self._hover = False
        self._apply_style()

    def dropEvent(self, event):
        self._hover = False
        self._apply_style()
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile()]
        if paths:
            self._on_files(paths)

    def set_dark(self, dark: bool):
        self._dark = dark
        self._apply_style()

    def retranslate(self):
        self.prompt.setText(t("imp.drop.hover") if self._hover else t("imp.drop.idle"))
        self.or_label.setText(t("imp.drop.or"))
        self.browse_btn.setText(t("imp.btn.browse"))

    def _apply_style(self):
        s = semantic(self._dark)
        border = s["primary"] if self._hover else s["dashed_border"]
        bg = s["info_bg"] if self._hover else s["surface_soft"]
        self.setStyleSheet(
            f"DropZone {{ border: 2px dashed {border}; border-radius: 14px; background: {bg}; }}"
            f"DropZone QLabel {{ background: transparent; border: none; color: {s['ink_faint']}; }}"
        )
        self.prompt.setText(t("imp.drop.hover") if self._hover else t("imp.drop.idle"))


class ImportMediaScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False

        self.bin_items = []      # {name, ext, status, codec, kind_key}
        self.pending = []        # queue of paths mid-import
        self.total = 0
        self.done = 0

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_import_tick)

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(14)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self.dropzone = DropZone(self._start_import)
        self.dropzone.browse_btn.clicked.connect(self._browse)
        self.outer.addWidget(self.dropzone)

        self.import_label = CaptionLabel()
        self.import_bar = QProgressBar()
        self.import_bar.setRange(0, 100)
        self.import_label.setVisible(False)
        self.import_bar.setVisible(False)
        self.outer.addWidget(self.import_label)
        self.outer.addWidget(self.import_bar)

        head = QHBoxLayout()
        self.bin_title = SectionLabel()
        head.addWidget(self.bin_title)
        self.bin_count = CaptionLabel()
        head.addWidget(self.bin_count)
        head.addStretch(1)
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_bin)
        head.addWidget(self.clear_btn)
        self.outer.addLayout(head)

        self.empty_label = CaptionLabel()
        self.outer.addWidget(self.empty_label)
        self.bin_container = QVBoxLayout()
        self.bin_container.setSpacing(8)
        self.outer.addLayout(self.bin_container)
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        self.retranslate()

    # ------------------------------------------------------------------
    def _browse(self):
        paths, _ = QFileDialog.getOpenFileNames(self, t("imp.dialog.title"), "", t("imp.dialog.filter"))
        if paths:
            self._start_import(paths)

    def _start_import(self, paths):
        self.pending += list(paths)
        self.total = self.done + len(self.pending)
        if not self._timer.isActive():
            self._timer.start()
        self._render()

    def _on_import_tick(self):
        if not self.pending:
            self._timer.stop()
            self._render()
            return
        path = self.pending.pop(0)
        self.bin_items.append(self._classify(path))
        self.done += 1
        self.import_bar.setValue(int(self.done / max(1, self.total) * 100))
        if not self.pending:
            self._timer.stop()
            self.done = 0
            self.total = 0
            imported = sum(1 for it in self.bin_items if it["status"] == "imported")
            show_toast(self, t("imp.imported_toast", n=imported), dark=self._dark)
        self._render()

    @staticmethod
    def _classify(path):
        name = path.replace("\\", "/").split("/")[-1] or path
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in SUPPORTED:
            return {"name": name, "ext": ext, "status": "unsupported", "codec": None, "kind_key": None}
        if "corrupt" in name.lower():
            return {"name": name, "ext": ext, "status": "failed", "codec": None, "kind_key": None}
        return {
            "name": name, "ext": ext, "status": "imported",
            "codec": CODEC_BY_EXT[ext], "kind_key": KIND_KEY_BY_EXT[ext],
        }

    def _remove(self, item):
        self.bin_items = [it for it in self.bin_items if it is not item]
        self._render()

    def _clear_bin(self):
        self.bin_items = []
        self._render()

    # ------------------------------------------------------------------
    def _render(self):
        importing = bool(self.pending) or self._timer.isActive()
        self.import_label.setVisible(importing)
        self.import_bar.setVisible(importing)
        if importing:
            self.import_label.setText(t("imp.importing", done=self.done, total=self.total))

        self.bin_count.setText(t("imp.bin.count", n=len(self.bin_items)))
        self.clear_btn.setVisible(bool(self.bin_items))
        self.empty_label.setVisible(not self.bin_items and not importing)

        clear_layout(self.bin_container)
        for item in self.bin_items:
            self.bin_container.addWidget(self._bin_card(item))

    def _bin_card(self, item):
        s = semantic(self._dark)
        card = Card(margins=(12, 10, 12, 10), spacing=4)
        row = QHBoxLayout()
        row.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(2)
        name = QLabel(item["name"])
        name.setStyleSheet("font-weight:700; font-size:13px;")
        name.setWordWrap(True)
        col.addWidget(name)
        detail = CaptionLabel()
        if item["status"] == "imported":
            detail.setText(t("imp.codec.detected", codec=item["codec"], kind=t(item["kind_key"])))
        elif item["status"] == "unsupported":
            detail.setText(t("imp.error.unsupported", ext=("." + item["ext"]) if item["ext"] else "?"))
            detail.setStyleSheet(f"color:{s['danger_fg_strong']}; font-size:11.5px;")
        else:
            detail.setText(t("imp.error.failed", name=item["name"]))
            detail.setStyleSheet(f"color:{s['danger_fg_strong']}; font-size:11.5px;")
        col.addWidget(detail)
        row.addLayout(col, 1)

        tone = {"imported": "success", "unsupported": "danger", "failed": "danger"}[item["status"]]
        key = {"imported": "imp.status.imported", "unsupported": "imp.status.unsupported", "failed": "imp.status.failed"}[item["status"]]
        badge = StatusBadge(t(key), tone=tone, dark=self._dark)
        row.addWidget(badge)

        remove_btn = QPushButton(t("imp.btn.remove"))
        remove_btn.clicked.connect(lambda _c=False, it=item: self._remove(it))
        row.addWidget(remove_btn)
        card.layout().addLayout(row)
        return card

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("imp.subtitle"))
        self.dropzone.retranslate()
        self.bin_title.setText(t("imp.bin.title"))
        self.clear_btn.setText(t("imp.btn.clear"))
        self.empty_label.setText(t("imp.bin.empty"))
        self._render()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self.dropzone.set_dark(dark)
        self._render()
