"""Native PySide6 port of §12 (Project Management — Save / Load / Backup).

Deliberately built from standard desktop building blocks — QFileDialog for
open/save, QMessageBox for the destructive-restore confirmation and the
unsaved-changes guard — rather than bespoke widgets. The two pieces the UI
audit flags as non-trivial get first-class treatment: the autosave-recovery
prompt on reopen (an inline banner, shown by default) and the destructive
Restore (a modal confirmation).

No real project store is wired in; open/save/backup/restore are simulated,
matching the other converted screens.
"""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, StatusBadge, clear_layout, show_toast
from common.scenes import scene_paths

THUMB_W, THUMB_H = 96, 54
TICK_MS = 90


class ProjectManagementScreen(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.NoFrame)
        self._dark = False
        self._scenes = scene_paths()

        # Seeded, simulated project store. Names are real Arabic content
        # (per the "test with real Arabic strings" cross-cutting rule), not
        # UI chrome, so they are intentionally not translated.
        self.projects = [
            {"name": "ملحمة النهر", "scenes": 14, "modified": "2026-07-14 09:12", "corrupt": False},
            {"name": "قصة المدينة", "scenes": 8, "modified": "2026-07-11 17:40", "corrupt": False},
            {"name": "حكاية الصحراء", "scenes": 14, "modified": "2026-07-06 20:05", "corrupt": True},
        ]
        self.current_name = self.projects[0]["name"]
        self.dirty = False
        self.loading = True
        self.recovery_visible = True
        self.busy = None          # None | ("backup" | "restore" | "autosave", label)
        self._progress = 0.0

        # Full autosave history for the current project (Task Q) — not just the
        # single latest recovery point the banner above surfaces. Most-recent
        # first; the first entry is the same point the recovery banner offers.
        self.autosaves = [
            {"time": "2026-07-14 09:10", "scenes": 14},
            {"time": "2026-07-14 08:37", "scenes": 13},
            {"time": "2026-07-14 07:52", "scenes": 11},
            {"time": "2026-07-13 21:15", "scenes": 8},
        ]

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_progress_tick)

        body = QWidget()
        self.setWidget(body)
        self.outer = QVBoxLayout(body)
        self.outer.setContentsMargins(0, 0, 4, 4)
        self.outer.setSpacing(14)

        self.subtitle = CaptionLabel()
        self.outer.addWidget(self.subtitle)

        self._build_recovery_banner()
        self._build_toolbar()
        self._build_busy_area()
        self._build_list_section()
        self._build_autosave_section()
        self.outer.addStretch(1)

        lang_manager.changed.connect(self._on_language_changed)
        # Brief loading state before the list appears (demonstrates §12 "Loading").
        QTimer.singleShot(500, self._finish_loading)
        self.retranslate()

    def _finish_loading(self):
        self.loading = False
        self._render()

    # ------------------------------------------------------------------
    def _build_recovery_banner(self):
        self.recovery_card = Card()
        self.recovery_card.setProperty("role", "cardFlat")
        lay = self.recovery_card.layout()
        self.recovery_title = SectionLabel()
        lay.addWidget(self.recovery_title)
        self.recovery_desc = CaptionLabel()
        lay.addWidget(self.recovery_desc)
        row = QHBoxLayout()
        self.recovery_btn = QPushButton()
        self.recovery_btn.setProperty("variant", "primary")
        self.recovery_btn.clicked.connect(self._recover)
        self.recovery_discard_btn = QPushButton()
        self.recovery_discard_btn.clicked.connect(self._discard_recovery)
        row.addWidget(self.recovery_btn)
        row.addWidget(self.recovery_discard_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.outer.addWidget(self.recovery_card)

    def _recover(self):
        self.recovery_visible = False
        self.current_name = self.projects[0]["name"]
        self.dirty = True  # recovered-but-unsaved work
        show_toast(self, t("pm.recovery.recovered_toast", name=self.projects[0]["name"]), dark=self._dark)
        self._render()

    def _discard_recovery(self):
        self.recovery_visible = False
        show_toast(self, t("pm.recovery.discarded_toast"), dark=self._dark)
        self._render()

    # ------------------------------------------------------------------
    def _build_toolbar(self):
        self.toolbar_card = Card()
        lay = self.toolbar_card.layout()
        row = QHBoxLayout()
        self.new_btn = QPushButton()
        self.new_btn.setProperty("variant", "primary")
        self.new_btn.clicked.connect(self._new_project)
        self.open_btn = QPushButton()
        self.open_btn.clicked.connect(self._open_project)
        self.save_btn = QPushButton()
        self.save_btn.clicked.connect(self._save_project)
        self.save_as_btn = QPushButton()
        self.save_as_btn.clicked.connect(self._save_as_project)
        for b in (self.new_btn, self.open_btn, self.save_btn, self.save_as_btn):
            row.addWidget(b)
        row.addStretch(1)
        self.dirty_badge = StatusBadge(dark=self._dark)
        row.addWidget(self.dirty_badge)
        lay.addLayout(row)
        self.folder_note = CaptionLabel()
        lay.addWidget(self.folder_note)
        self.outer.addWidget(self.toolbar_card)

    def _build_busy_area(self):
        self.busy_label = CaptionLabel()
        self.busy_bar = QProgressBar()
        self.busy_bar.setRange(0, 100)
        self.outer.addWidget(self.busy_label)
        self.outer.addWidget(self.busy_bar)
        self.busy_label.setVisible(False)
        self.busy_bar.setVisible(False)

    def _build_list_section(self):
        head = QHBoxLayout()
        self.list_title = SectionLabel()
        head.addWidget(self.list_title)
        head.addStretch(1)
        self.outer.addLayout(head)

        self.loading_label = CaptionLabel()
        self.outer.addWidget(self.loading_label)
        self.empty_label = CaptionLabel()
        self.outer.addWidget(self.empty_label)
        self.list_container = QVBoxLayout()
        self.list_container.setSpacing(10)
        self.outer.addLayout(self.list_container)

    def _build_autosave_section(self):
        self.autosave_title = SectionLabel()
        self.outer.addWidget(self.autosave_title)
        self.autosave_desc = CaptionLabel()
        self.outer.addWidget(self.autosave_desc)
        self.autosave_empty = CaptionLabel()
        self.outer.addWidget(self.autosave_empty)
        self.autosave_container = QVBoxLayout()
        self.autosave_container.setSpacing(8)
        self.outer.addLayout(self.autosave_container)

    def _render_autosaves(self):
        self.autosave_empty.setVisible(not self.autosaves)
        clear_layout(self.autosave_container)
        for i, snap in enumerate(self.autosaves):
            card = Card(flat=True, margins=(12, 8, 12, 8), spacing=6)
            row = QHBoxLayout()
            label = QLabel(t("pm.autosave.snapshot", time=snap["time"]))
            label.setStyleSheet("font-weight:600;")
            row.addWidget(label)
            if i == 0:
                row.addWidget(StatusBadge(t("pm.autosave.current"), tone="info", dark=self._dark))
            row.addStretch(1)
            meta = CaptionLabel(t("pm.project.scenes", n=snap["scenes"]))
            row.addWidget(meta)
            restore_btn = QPushButton(t("pm.autosave.restore"))
            restore_btn.clicked.connect(lambda _c=False, s=snap: self._restore_autosave(s))
            restore_btn.setEnabled(not self.busy)
            row.addWidget(restore_btn)
            card.layout().addLayout(row)
            self.autosave_container.addWidget(card)

    def _restore_autosave(self, snap):
        if self.busy:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(t("pm.restore.confirm.title"))
        box.setText(t("pm.autosave.confirm.body", name=self.current_name, time=snap["time"]))
        ok_btn = box.addButton(t("pm.restore.confirm.ok"), QMessageBox.DestructiveRole)
        box.addButton(t("pm.restore.confirm.cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is ok_btn:
            self.busy = ("autosave", snap["time"])
            self._progress = 0.0
            self._render()
            self._timer.start()

    # ------------------------------------------------------------------
    # Toolbar actions
    def _new_project(self):
        self._guard_unsaved(self._do_new_project)

    def _do_new_project(self):
        n = len(self.projects) + 1
        name = f"مشروع جديد {n}"
        self.projects.insert(0, {"name": name, "scenes": 0, "modified": self._now(), "corrupt": False})
        self.current_name = name
        self.dirty = True
        show_toast(self, t("pm.new.created_toast", name=name), dark=self._dark)
        self._render()

    def _open_project(self):
        self._guard_unsaved(self._do_open_dialog)

    def _do_open_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, t("pm.toolbar.open"), "", "project.json (project.json);;JSON (*.json)")
        if not path:
            return
        self.current_name = path.replace("\\", "/").split("/")[-2] if "/" in path.replace("\\", "/") else path
        self.dirty = False
        show_toast(self, t("pm.open.opened_toast", name=self.current_name), dark=self._dark)
        self._render()

    def _save_project(self):
        if not self.dirty:
            return
        self.dirty = False
        for p in self.projects:
            if p["name"] == self.current_name:
                p["modified"] = self._now()
        show_toast(self, t("pm.save.saved_toast", name=self.current_name), dark=self._dark)
        self._render()

    def _save_as_project(self):
        path, _ = QFileDialog.getSaveFileName(self, t("pm.toolbar.save_as"), "project.json", "JSON (*.json)")
        if not path:
            return
        self.dirty = False
        show_toast(self, t("pm.save.saved_toast", name=self.current_name), dark=self._dark)
        self._render()

    def _guard_unsaved(self, proceed):
        """Warn-on-discard guard (§12 'Unsaved changes' state)."""
        if not self.dirty:
            proceed()
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(t("pm.unsaved.title"))
        box.setText(t("pm.unsaved.body", name=self.current_name))
        save_btn = box.addButton(t("pm.unsaved.save"), QMessageBox.AcceptRole)
        discard_btn = box.addButton(t("pm.unsaved.discard"), QMessageBox.DestructiveRole)
        box.addButton(t("pm.unsaved.cancel"), QMessageBox.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is save_btn:
            self._save_project()
            proceed()
        elif clicked is discard_btn:
            self.dirty = False
            proceed()
        # Cancel: do nothing.

    # ------------------------------------------------------------------
    # Per-project actions
    def _open_one(self, project):
        if project["corrupt"]:
            QMessageBox.warning(self, t("pm.corrupt.title"), t("pm.corrupt.body", name=project["name"]))
            return
        self.current_name = project["name"]
        self.dirty = False
        show_toast(self, t("pm.open.opened_toast", name=project["name"]), dark=self._dark)
        self._render()

    def _backup_one(self, project):
        if self.busy:
            return
        self.busy = ("backup", project["name"])
        self._progress = 0.0
        self._render()
        self._timer.start()

    def _restore_one(self, project):
        if self.busy:
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(t("pm.restore.confirm.title"))
        box.setText(t("pm.restore.confirm.body", name=project["name"]))
        ok_btn = box.addButton(t("pm.restore.confirm.ok"), QMessageBox.DestructiveRole)
        box.addButton(t("pm.restore.confirm.cancel"), QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is ok_btn:
            self.busy = ("restore", project["name"])
            self._progress = 0.0
            self._render()
            self._timer.start()

    def _delete_one(self, project):
        if self.busy:
            return
        self.projects = [p for p in self.projects if p is not project]
        show_toast(self, t("pm.delete.deleted_toast", name=project["name"]), dark=self._dark)
        self._render()

    def _on_progress_tick(self):
        self._progress = min(1.0, self._progress + 0.08)
        self.busy_bar.setValue(int(self._progress * 100))
        if self._progress >= 1.0:
            self._timer.stop()
            kind, name = self.busy
            self.busy = None
            if kind == "backup":
                stamp = datetime.now().strftime("%Y%m%d-%H%M")
                show_toast(self, t("pm.backup.done_toast", file=f"{name}_{stamp}.zip"), dark=self._dark)
            elif kind == "autosave":
                self.dirty = True  # restored-but-unsaved, like the recovery banner
                show_toast(self, t("pm.autosave.restored_toast", time=name), dark=self._dark)
            else:
                show_toast(self, t("pm.restore.done_toast", name=name), dark=self._dark)
            self._render()

    # ------------------------------------------------------------------
    def _render(self):
        self.recovery_card.setVisible(self.recovery_visible and not self.loading)

        # dirty indicator
        self.dirty_badge.setText(t("pm.dirty.badge") if self.dirty else t("pm.saved.badge"))
        self.dirty_badge.set_tone("warning" if self.dirty else "success", self._dark)
        self.save_btn.setEnabled(self.dirty and not self.busy)

        # busy area
        if self.busy:
            kind, name = self.busy
            key = "pm.backup.progress" if kind == "backup" else "pm.restore.progress"
            self.busy_label.setText(t(key, name=name))
        self.busy_label.setVisible(bool(self.busy))
        self.busy_bar.setVisible(bool(self.busy))

        # toolbar disabled while a heavy op runs
        for b in (self.new_btn, self.open_btn, self.save_as_btn):
            b.setEnabled(not self.busy)

        self.loading_label.setVisible(self.loading)
        self.empty_label.setVisible(not self.loading and not self.projects)

        clear_layout(self.list_container)
        if self.loading:
            self.autosave_title.setVisible(False)
            self.autosave_desc.setVisible(False)
            self.autosave_empty.setVisible(False)
            clear_layout(self.autosave_container)
            return
        for project in self.projects:
            self.list_container.addWidget(self._project_card(project))

        self.autosave_title.setVisible(True)
        self.autosave_desc.setVisible(True)
        self._render_autosaves()

    def _project_card(self, project):
        card = Card(margins=(12, 10, 12, 10), spacing=8)
        row = QHBoxLayout()
        row.setSpacing(12)

        thumb = QLabel()
        thumb.setFixedSize(THUMB_W, THUMB_H)
        thumb.setStyleSheet("border-radius:8px;")
        if self._scenes:
            idx = self.projects.index(project) % len(self._scenes)
            pix = QPixmap(str(self._scenes[idx])).scaled(
                THUMB_W, THUMB_H, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            thumb.setPixmap(pix)
        row.addWidget(thumb)

        info = QVBoxLayout()
        info.setSpacing(2)
        name_row = QHBoxLayout()
        name = QLabel(project["name"])
        name.setStyleSheet("font-weight:700; font-size:13.5px;")
        name_row.addWidget(name)
        if project["name"] == self.current_name:
            open_dot = QLabel("•")
            open_dot.setStyleSheet(f"color:{semantic(self._dark)['primary']}; font-weight:900;")
            name_row.addWidget(open_dot)
        name_row.addStretch(1)
        if project["corrupt"]:
            badge = StatusBadge(t("pm.status.corrupt"), tone="danger", dark=self._dark)
            name_row.addWidget(badge)
        info.addLayout(name_row)
        meta = CaptionLabel(
            t("pm.project.scenes", n=project["scenes"]) + " · " + t("pm.project.modified", date=project["modified"])
        )
        info.addWidget(meta)
        row.addLayout(info, 1)
        card.layout().addLayout(row)

        actions = QHBoxLayout()
        open_btn = QPushButton(t("pm.btn.open"))
        open_btn.clicked.connect(lambda _c=False, p=project: self._open_one(p))
        backup_btn = QPushButton(t("pm.btn.backup"))
        backup_btn.clicked.connect(lambda _c=False, p=project: self._backup_one(p))
        restore_btn = QPushButton(t("pm.btn.restore"))
        restore_btn.clicked.connect(lambda _c=False, p=project: self._restore_one(p))
        delete_btn = QPushButton(t("pm.btn.delete"))
        delete_btn.setProperty("variant", "danger")
        delete_btn.clicked.connect(lambda _c=False, p=project: self._delete_one(p))
        for b in (open_btn, backup_btn, restore_btn, delete_btn):
            b.setEnabled(not self.busy)
            actions.addWidget(b)
        actions.addStretch(1)
        card.layout().addLayout(actions)
        return card

    @staticmethod
    def _now():
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("pm.subtitle"))
        self.recovery_title.setText(t("pm.recovery.title"))
        self.recovery_desc.setText(t("pm.recovery.desc", name=self.projects[0]["name"], time="09:10"))
        self.recovery_btn.setText(t("pm.recovery.recover"))
        self.recovery_discard_btn.setText(t("pm.recovery.discard"))
        self.new_btn.setText(t("pm.toolbar.new"))
        self.open_btn.setText(t("pm.toolbar.open"))
        self.save_btn.setText(t("pm.toolbar.save"))
        self.save_as_btn.setText(t("pm.toolbar.save_as"))
        self.folder_note.setText(t("pm.folder.note"))
        self.list_title.setText(t("pm.list.title"))
        self.loading_label.setText(t("pm.loading"))
        self.empty_label.setText(t("pm.empty"))
        self.autosave_title.setText(t("pm.autosave.title"))
        self.autosave_desc.setText(t("pm.autosave.desc"))
        self.autosave_empty.setText(t("pm.autosave.empty"))
        self._render()

    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render()
