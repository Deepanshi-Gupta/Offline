"""Native PySide6 port of smart_director_app.py (§8 of the UI audit) — the
Smart Director / Pipeline Orchestrator, the screen users stare at for 45+
minutes.

This is a faithful conversion of the Streamlit source: same 14-scene ×
4-stage pipeline, same Auto/Manual modes, same per-stage skip controls,
same scripted failure at scene 12 during Animation, and the same
retry / skip-scene / abort / pause / resume / restart controls. Only the
UI toolkit changed (Streamlit → Qt) and the business logic is preserved.

Architecture parity with the original
-------------------------------------
The Streamlit version advanced the pipeline by exactly one scene×stage
unit per script run, then called st.rerun(), so a Pause/Cancel click was
picked up at the next unit boundary (real, not fake, responsiveness).

Here the same one-unit-per-tick model runs on a QTimer instead of
st.rerun(): each timeout advances the pipeline by one unit and re-renders.
Because Pause/Cancel just flip PipelineState.status and the timer checks
status before advancing, a click is honoured within one tick (~120 ms) —
identical responsiveness, no blocking GUI-thread loop. PipelineState holds
all logic UI-free (the st.session_state replacement) and returns structured
events the screen turns into log lines, keeping state testable in isolation.

Layout maps the handoff's target structure into this one screen:
    now-banner (header)  ·  ProgressTrackerWidget (left Task Timeline)
    dashboard (centre)   ·  controls (right)  ·  logs (bottom)
"""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from common.desktop import render_activity
from common.i18n import lang_manager, t
from common.qt_theme import semantic
from common.qt_widgets import Card, CaptionLabel, SectionLabel, clear_layout, repolish

# (stable id, i18n key) — id keeps skip-state/grid indexing language-stable
STAGES = [
    ("image", "sd.stage.image"),
    ("animation", "sd.stage.animation"),
    ("voice", "sd.stage.voice"),
    ("compilation", "sd.stage.compilation"),
]
NUM_SCENES = 14
FAIL_SCENE_IDX = 11  # Scene 12 — the doc's own "failure at scene 12 of 14" example
FAIL_STAGE_IDX = 1  # Animation
SIM_MINUTES_PER_UNIT = 0.8  # cosmetic — 14 × 4 × 0.8 ≈ 45 min, matching the real spec
TICK_MS = 120


def status_style(dark: bool) -> dict:
    """Per-status (icon, foreground, background) for grid/stepper cells,
    themed off the shared semantic palette so dark mode is coherent."""
    s = semantic(dark)
    return {
        "pending": ("○", s["ink_fainter"], s["surface_soft"]),
        "running": ("⏳", "#FFFFFF", s["primary"]),
        "done": ("✓", "#FFFFFF", "#22B35E" if not dark else "#2f9e5f"),
        "skipped": ("–", s["ink_fainter"], s["surface_muted"]),
        "failed": ("✕", "#FFFFFF", s["danger_fg"]),
    }


# now-banner tone per pipeline status -> (bg, border, fg) semantic keys
BANNER_TONE = {
    "idle": ("info_bg", "info_border", "info_fg"),
    "running": ("info_bg", "info_border", "info_fg"),
    "paused": ("warning_bg", "warning_border", "warning_fg_strong"),
    "failed": ("danger_bg", "danger_border", "danger_fg_strong"),
    "cancelled": ("surface_muted", "border", "ink_soft"),
    "complete": ("success_bg", "success_border", "success_fg_strong"),
}


# =====================================================================
# Pipeline state / logic — the st.session_state replacement (UI-free).
# advance_one_step() returns structured events the screen logs & renders.
# =====================================================================
class PipelineState:
    def __init__(self):
        self.mode = "auto"  # "auto" | "manual"
        self.status = "idle"  # idle, running, paused, failed, cancelled, complete
        self.cur_scene = 0
        self.cur_stage = 0
        self.grid = [["pending"] * len(STAGES) for _ in range(NUM_SCENES)]
        self.stage_skip = {sid: False for sid, _key in STAGES}
        self.fail_triggered = False

    def reset(self):
        """Reset run progress; preserves mode and per-stage skip choices
        (matching the Streamlit reset_all())."""
        self.status = "idle"
        self.cur_scene = 0
        self.cur_stage = 0
        self.grid = [["pending"] * len(STAGES) for _ in range(NUM_SCENES)]
        self.fail_triggered = False

    def _advance_to_next_stage(self, events):
        self.cur_scene = 0
        if self.cur_stage < len(STAGES) - 1:
            self.cur_stage += 1
            if self.mode == "manual":
                self.status = "paused"
        else:
            self.status = "complete"
            events.append({"type": "complete"})

    def _advance_scene_or_stage(self, events):
        if self.cur_scene < NUM_SCENES - 1:
            self.cur_scene += 1
        else:
            self._advance_to_next_stage(events)

    def advance_one_step(self):
        """Advance the pipeline by exactly one scene×stage unit. Returns a
        list of event dicts describing what happened, for logging."""
        events = []
        stage_idx = self.cur_stage
        scene_idx = self.cur_scene

        if self.stage_skip[STAGES[stage_idx][0]]:
            for s in range(NUM_SCENES):
                if self.grid[s][stage_idx] == "pending":
                    self.grid[s][stage_idx] = "skipped"
            events.append({"type": "skip_stage", "stage": stage_idx})
            self._advance_to_next_stage(events)
            return events

        if scene_idx == FAIL_SCENE_IDX and stage_idx == FAIL_STAGE_IDX and not self.fail_triggered:
            self.grid[scene_idx][stage_idx] = "failed"
            self.fail_triggered = True
            self.status = "failed"
            events.append({"type": "fail", "scene": scene_idx, "stage": stage_idx})
            return events

        self.grid[scene_idx][stage_idx] = "done"
        events.append({"type": "done", "scene": scene_idx, "stage": stage_idx})
        self._advance_scene_or_stage(events)
        return events

    def completed_units(self) -> int:
        return sum(1 for row in self.grid for c in row if c in ("done", "skipped"))


# =====================================================================
# ProgressTrackerWidget — the left-side Task Timeline panel.
# Builds the 14×4 scene queue grid once, then only re-styles cells on
# update() (no per-tick rebuild — keeps a 45-minute run cheap).
# =====================================================================
class ProgressTrackerWidget(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self.setFixedWidth(320)
        self._dark = False

        body = QWidget()
        self.setWidget(body)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(4, 4, 8, 4)
        outer.setSpacing(10)

        self.title = SectionLabel()
        outer.addWidget(self.title)
        self.queue_label = CaptionLabel()
        outer.addWidget(self.queue_label)

        grid_card = Card(flat=True, margins=(8, 8, 8, 8), spacing=0)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(5)
        grid_card.layout().addLayout(self.grid)

        # header row: blank corner + stage names
        self._stage_headers = []
        for i, (_sid, _key) in enumerate(STAGES):
            h = QLabel()
            h.setAlignment(Qt.AlignCenter)
            h.setProperty("role", "caption")
            self.grid.addWidget(h, 0, i + 1)
            self._stage_headers.append(h)

        # 14 scene rows
        self._scene_labels = []
        self._cells = []
        for s in range(NUM_SCENES):
            lbl = QLabel()
            lbl.setProperty("class", "rowTitle")
            self.grid.addWidget(lbl, s + 1, 0)
            self._scene_labels.append(lbl)
            row_cells = []
            for i in range(len(STAGES)):
                cell = QLabel()
                cell.setAlignment(Qt.AlignCenter)
                cell.setFixedSize(28, 26)
                self.grid.addWidget(cell, s + 1, i + 1)
                row_cells.append(cell)
            self._cells.append(row_cells)

        outer.addWidget(grid_card)
        outer.addStretch(1)
        self.retranslate()

    def retranslate(self):
        self.title.setText(t("sd.timeline.title"))
        self.queue_label.setText(t("sd.queue.label"))
        for i, (_sid, key) in enumerate(STAGES):
            self._stage_headers[i].setText(t(key))
        for s in range(NUM_SCENES):
            self._scene_labels[s].setText(t("sd.scene", n=s + 1))

    def update_grid(self, state: PipelineState, dark: bool):
        self._dark = dark
        styles = status_style(dark)
        s = semantic(dark)
        active = state.status in ("running", "failed")
        for row in range(NUM_SCENES):
            for col in range(len(STAGES)):
                icon, fg, bg = styles[state.grid[row][col]]
                is_current = active and row == state.cur_scene and col == state.cur_stage
                border = s["primary"] if is_current else "transparent"
                self._cells[row][col].setText(icon)
                self._cells[row][col].setStyleSheet(
                    f"background:{bg}; color:{fg}; border-radius:7px;"
                    f" border:2px solid {border}; font-size:13px; font-weight:700;"
                )


# =====================================================================
# The screen itself — owns PipelineState, the tick timer, and all widgets.
# =====================================================================
class SmartDirectorScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._dark = False
        self.state = PipelineState()
        self._toasted_complete = False
        # a prior 45-min run was interrupted and autosaved — offer to resume
        # right here on the pipeline screen, not only from the Projects list
        self.recovery_visible = True
        self._log_entries = []  # list of (key, static_kwargs, dyn_kwargs)

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)

        self._build_ui()
        lang_manager.changed.connect(self._on_language_changed)
        self._add_log("sd.log.reset")
        self.retranslate()

    # ------------------------------------------------------------------
    # construction
    # ------------------------------------------------------------------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        self.subtitle = CaptionLabel()
        root.addWidget(self.subtitle)

        # crash-recovery banner — contextual "Resume from Autosave?" on the
        # pipeline screen itself (Task 9), same inline-banner pattern as the
        # Projects-list recovery prompt.
        self.recovery_card = QFrame()
        rec_lay = QVBoxLayout(self.recovery_card)
        rec_lay.setContentsMargins(16, 12, 16, 12)
        rec_lay.setSpacing(6)
        self.recovery_title = SectionLabel()
        rec_lay.addWidget(self.recovery_title)
        self.recovery_desc = CaptionLabel()
        self.recovery_desc.setWordWrap(True)
        rec_lay.addWidget(self.recovery_desc)
        rec_row = QHBoxLayout()
        self.recovery_btn = QPushButton()
        self.recovery_btn.setProperty("variant", "primary")
        self.recovery_btn.setCursor(Qt.PointingHandCursor)
        self.recovery_btn.clicked.connect(self._resume_from_autosave)
        self.recovery_discard_btn = QPushButton()
        self.recovery_discard_btn.setCursor(Qt.PointingHandCursor)
        self.recovery_discard_btn.clicked.connect(self._discard_autosave)
        rec_row.addWidget(self.recovery_btn)
        rec_row.addWidget(self.recovery_discard_btn)
        rec_row.addStretch(1)
        rec_lay.addLayout(rec_row)
        root.addWidget(self.recovery_card)

        # now-banner — "what is it doing right now" must be unmistakable
        self.banner = QFrame()
        banner_lay = QHBoxLayout(self.banner)
        banner_lay.setContentsMargins(16, 13, 16, 13)
        self.banner_label = QLabel()
        self.banner_label.setWordWrap(True)
        banner_lay.addWidget(self.banner_label)
        root.addWidget(self.banner)

        # body: left timeline | centre dashboard | right controls
        body = QHBoxLayout()
        body.setSpacing(16)
        self.tracker = ProgressTrackerWidget()
        body.addWidget(self.tracker)
        body.addWidget(self._build_center(), 1)
        body.addWidget(self._build_controls())
        root.addLayout(body, 1)

        # bottom: logs
        root.addWidget(self._build_logs())

    def _build_center(self) -> QWidget:
        card = Card()
        lay = card.layout()

        gpu_row = QHBoxLayout()
        self.gpu_pill = QLabel()
        self.gpu_pill.setObjectName("gpuPill")
        gpu_row.addWidget(self.gpu_pill)
        gpu_row.addStretch(1)
        lay.addLayout(gpu_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, NUM_SCENES * len(STAGES))
        self.progress.setTextVisible(True)
        lay.addWidget(self.progress)

        # current-scene stepper — zoomed-in detail for the active scene
        stepper_row = QHBoxLayout()
        stepper_row.setSpacing(8)
        self._stepper = []
        for i in range(len(STAGES)):
            chip = QLabel()
            chip.setAlignment(Qt.AlignCenter)
            chip.setWordWrap(True)
            chip.setMinimumHeight(40)
            stepper_row.addWidget(chip, 1)
            self._stepper.append(chip)
        lay.addLayout(stepper_row)

        self.detail_caption = CaptionLabel()
        lay.addWidget(self.detail_caption)
        lay.addStretch(1)
        return card

    def _build_controls(self) -> QWidget:
        card = Card()
        card.setFixedWidth(280)
        lay = card.layout()

        self.mode_label = SectionLabel()
        lay.addWidget(self.mode_label)
        mode_row = QHBoxLayout()
        self.auto_btn = QPushButton()
        self.auto_btn.setCheckable(False)
        self.auto_btn.clicked.connect(lambda: self._set_mode("auto"))
        self.manual_btn = QPushButton()
        self.manual_btn.clicked.connect(lambda: self._set_mode("manual"))
        mode_row.addWidget(self.auto_btn)
        mode_row.addWidget(self.manual_btn)
        lay.addLayout(mode_row)
        self.mode_caption = CaptionLabel()
        lay.addWidget(self.mode_caption)

        self.skip_label = SectionLabel()
        lay.addWidget(self.skip_label)
        self._skip_checks = {}
        for sid, _key in STAGES:
            cb = QCheckBox()
            cb.toggled.connect(lambda checked, s=sid: self._set_skip(s, checked))
            lay.addWidget(cb)
            self._skip_checks[sid] = cb

        # manual-override persistence state — mode + per-stage skip choices
        # survive reset()/restart/new-batch; make that visible (Task 9)
        self.persist_note = CaptionLabel()
        self.persist_note.setWordWrap(True)
        lay.addWidget(self.persist_note)

        # per-state action area (rebuilt on each render — a few buttons only)
        self.actions_prompt = QLabel()
        self.actions_prompt.setWordWrap(True)
        self.actions_prompt.setVisible(False)
        lay.addWidget(self.actions_prompt)
        self.actions_container = QVBoxLayout()
        self.actions_container.setSpacing(8)
        lay.addLayout(self.actions_container)
        lay.addStretch(1)
        return card

    def _build_logs(self) -> QWidget:
        card = Card(margins=(14, 10, 14, 12), spacing=6)
        lay = card.layout()
        head = QHBoxLayout()
        self.logs_title = SectionLabel()
        self.clear_btn = QPushButton()
        self.clear_btn.clicked.connect(self._clear_logs)
        head.addWidget(self.logs_title)
        head.addStretch(1)
        head.addWidget(self.clear_btn)
        lay.addLayout(head)
        self.logs_view = QPlainTextEdit()
        self.logs_view.setReadOnly(True)
        self.logs_view.setFixedHeight(120)
        lay.addWidget(self.logs_view)
        return card

    # ------------------------------------------------------------------
    # logging (bilingual — entries retranslate on language flip)
    # ------------------------------------------------------------------
    def _add_log(self, key: str, dyn: dict = None, **kwargs):
        """dyn maps a format field to an i18n key resolved at render time
        (so e.g. the stage name follows the current language)."""
        self._log_entries.append((key, kwargs, dyn or {}))
        self._render_logs()

    def _render_logs(self):
        lines = []
        for key, kwargs, dyn in self._log_entries:
            resolved = {**kwargs, **{k: t(v) for k, v in dyn.items()}}
            lines.append(t(key, **resolved))
        self.logs_view.setPlainText("\n".join(lines))
        self.logs_view.verticalScrollBar().setValue(self.logs_view.verticalScrollBar().maximum())

    def _clear_logs(self):
        self._log_entries = [("sd.logs.cleared", {}, {})]
        self._render_logs()

    def _log_events(self, events):
        for ev in events:
            typ = ev["type"]
            if typ == "done":
                self._add_log("sd.log.done", scene=ev["scene"] + 1, dyn={"stage": STAGES[ev["stage"]][1]})
            elif typ == "skip_stage":
                self._add_log("sd.log.skip_stage", dyn={"stage": STAGES[ev["stage"]][1]})
            elif typ == "fail":
                self._add_log("sd.log.fail", scene=ev["scene"] + 1, dyn={"stage": STAGES[ev["stage"]][1]})
            elif typ == "complete":
                self._add_log("sd.log.complete")

    # ------------------------------------------------------------------
    # pipeline driving
    # ------------------------------------------------------------------
    def _on_tick(self):
        if self.state.status != "running":
            self._timer.stop()
            render_activity.end("smart_director")
            return
        events = self.state.advance_one_step()
        self._log_events(events)
        if self.state.status == "complete" and not self._toasted_complete:
            self._toasted_complete = True
        # native OS toast on the pipeline's terminal transitions — this is the
        # 45-minute render, so the user is likely doing something else (gaps
        # A2/A3): tell them, and stop holding the machine awake.
        for ev in events:
            if ev["type"] == "complete":
                render_activity.notify(t("nav.smart_director"), success=True, detail=t("sd.log.complete"))
            elif ev["type"] == "fail":
                detail = f"{t('sd.scene', n=ev['scene'] + 1)} — {t(STAGES[ev['stage']][1])}"
                render_activity.notify(t("nav.smart_director"), success=False, detail=detail)
        self._render_dynamic()
        self._sync_timer()

    def _sync_timer(self):
        # Single chokepoint every state transition passes through, so the
        # system-sleep guard is held exactly while the pipeline is running.
        # begin()/end() are idempotent per token, so repeated calls are safe.
        if self.state.status == "running":
            render_activity.begin("smart_director")
            if not self._timer.isActive():
                self._timer.start()
        else:
            render_activity.end("smart_director")
            self._timer.stop()

    def _set_mode(self, mode: str):
        if self._locked():
            return
        self.state.mode = mode
        self._render_dynamic()

    def _set_skip(self, stage_id: str, checked: bool):
        self.state.stage_skip[stage_id] = checked

    def _locked(self) -> bool:
        return self.state.status not in ("idle", "cancelled", "complete")

    # ---- crash recovery (contextual "Resume from Autosave?") ----
    def _render_recovery(self):
        self.recovery_card.setVisible(self.recovery_visible)
        if not self.recovery_visible:
            return
        s = semantic(self._dark)
        self.recovery_card.setStyleSheet(
            f"background:{s['warning_bg']}; border:1px solid {s['warning_border']}; border-radius:14px;"
        )
        for w in (self.recovery_title, self.recovery_desc):
            w.setStyleSheet(f"color:{s['warning_fg_strong']}; background:transparent; border:none;")

    def _resume_from_autosave(self):
        """Restore the interrupted run to a coherent mid-pipeline paused state
        (image stage done for all scenes, animation done up to Scene 6), then
        let the user continue from there. reset() preserves the persisted
        mode + skip overrides."""
        self.recovery_visible = False
        st = self.state
        st.reset()
        resume_scene, resume_stage = 5, 1  # Scene 6, Animation
        for scene in range(NUM_SCENES):
            for stage in range(resume_stage):
                st.grid[scene][stage] = "done"
        for scene in range(resume_scene):
            st.grid[scene][resume_stage] = "done"
        st.cur_scene = resume_scene
        st.cur_stage = resume_stage
        st.status = "paused"
        self._toasted_complete = False
        self._add_log("sd.log.recovered", scene=resume_scene + 1, dyn={"stage": STAGES[resume_stage][1]})
        self._render_recovery()
        self._render_dynamic()
        self._sync_timer()

    def _discard_autosave(self):
        self.recovery_visible = False
        self._add_log("sd.log.recovery_discarded")
        self._render_recovery()

    # ---- action handlers (one per Streamlit per-state button) ----
    def _start(self):
        self.recovery_visible = False
        self._render_recovery()
        self.state.reset()
        self._toasted_complete = False
        self.state.status = "running"
        self._add_log("sd.log.start", dyn={"mode": "sd.mode.auto_word" if self.state.mode == "auto" else "sd.mode.manual_word"})
        self._render_dynamic()
        self._sync_timer()

    def _pause(self):
        self.state.status = "paused"
        self._add_log("sd.log.pause")
        self._render_dynamic()
        self._sync_timer()

    def _cancel(self):
        self.state.status = "cancelled"
        self._add_log("sd.log.cancel")
        self._render_dynamic()
        self._sync_timer()

    def _next_step(self):
        self.state.status = "running"
        self._add_log("sd.log.resume")
        self._render_dynamic()
        self._sync_timer()

    def _retry(self):
        self.state.grid[FAIL_SCENE_IDX][FAIL_STAGE_IDX] = "pending"
        self.state.status = "running"
        self._add_log("sd.log.retry", scene=FAIL_SCENE_IDX + 1, dyn={"stage": STAGES[FAIL_STAGE_IDX][1]})
        self._render_dynamic()
        self._sync_timer()

    def _skip_scene(self):
        self.state.grid[FAIL_SCENE_IDX][FAIL_STAGE_IDX] = "skipped"
        self._add_log("sd.log.skip_scene", scene=FAIL_SCENE_IDX + 1, dyn={"stage": STAGES[FAIL_STAGE_IDX][1]})
        events = []
        self.state._advance_scene_or_stage(events)
        self._log_events(events)
        self.state.status = "running"
        self._render_dynamic()
        self._sync_timer()

    def _resume(self):
        self.state.status = "running"
        self._add_log("sd.log.resume")
        self._render_dynamic()
        self._sync_timer()

    def _restart(self):
        self.recovery_visible = False
        self._render_recovery()
        self.state.reset()
        self._toasted_complete = False
        self._add_log("sd.log.reset")
        self._render_dynamic()
        self._sync_timer()

    # ------------------------------------------------------------------
    # rendering
    # ------------------------------------------------------------------
    def retranslate(self):
        self.subtitle.setText(t("sd.subtitle"))
        self.recovery_title.setText(t("sd.recovery.title"))
        self.recovery_desc.setText(t("sd.recovery.desc", scene=6, stage=t(STAGES[1][1])))
        self.recovery_btn.setText(t("sd.recovery.resume"))
        self.recovery_discard_btn.setText(t("sd.recovery.discard"))
        self._render_recovery()
        self.mode_label.setText(t("sd.mode.label"))
        self.auto_btn.setText(t("sd.mode.auto"))
        self.manual_btn.setText(t("sd.mode.manual"))
        self.mode_caption.setText(t("sd.mode.caption"))
        self.skip_label.setText(t("sd.skip.label"))
        for sid, key in STAGES:
            self._skip_checks[sid].setText(t(key))
        self.logs_title.setText(t("sd.logs.title"))
        self.clear_btn.setText(t("sd.logs.clear"))
        self.tracker.retranslate()
        self._render_logs()
        self._render_dynamic()

    def _banner_text(self) -> str:
        st = self.state
        scene, stage = st.cur_scene, st.cur_stage
        stage_name = t(STAGES[stage][1])
        if st.status == "idle":
            return t("sd.banner.idle")
        if st.status == "running":
            return t("sd.banner.running", scene=scene + 1, total=NUM_SCENES, stage=stage_name)
        if st.status == "paused":
            if scene == 0 and stage > 0:
                return t("sd.banner.paused_after_stage", prev=t(STAGES[stage - 1][1]), stage=stage_name)
            return t("sd.banner.paused_at_scene", scene=scene + 1, stage=stage_name)
        if st.status == "failed":
            return t(
                "sd.banner.failed",
                scene=FAIL_SCENE_IDX + 1,
                total=NUM_SCENES,
                stage=t(STAGES[FAIL_STAGE_IDX][1]),
                done=FAIL_SCENE_IDX,
            )
        if st.status == "cancelled":
            return t("sd.banner.cancelled", done=st.completed_units(), total=NUM_SCENES * len(STAGES))
        return t("sd.banner.complete")

    def _render_dynamic(self):
        st = self.state
        s = semantic(self._dark)

        # banner
        bg_k, border_k, fg_k = BANNER_TONE[st.status]
        self.banner.setStyleSheet(
            f"background:{s[bg_k]}; border:1px solid {s[border_k]}; border-radius:14px;"
        )
        self.banner_label.setStyleSheet(f"color:{s[fg_k]}; font-size:15px; font-weight:700; background:transparent; border:none;")
        self.banner_label.setText(self._banner_text())

        # GPU pill
        gpu_active = st.status == "running"
        self.gpu_pill.setText(t("sd.gpu.active") if gpu_active else t("sd.gpu.idle"))
        pill_bg, pill_fg = (s["info_bg"], s["info_fg"]) if gpu_active else (s["surface_muted"], s["ink_faint"])
        self.gpu_pill.setStyleSheet(
            f"#gpuPill {{ background:{pill_bg}; color:{pill_fg}; border-radius:999px;"
            " padding:3px 12px; font-size:11.5px; font-weight:600; }}"
        )

        # overall progress + ETA
        total_units = NUM_SCENES * len(STAGES)
        done = st.completed_units()
        eta = (total_units - done) * SIM_MINUTES_PER_UNIT
        self.progress.setValue(done)
        self.progress.setFormat(t("sd.progress.text", done=done, total=total_units, eta=f"{eta:.0f}"))

        # current-scene stepper
        styles = status_style(self._dark)
        active = st.status in ("running", "failed")
        for i, (_sid, key) in enumerate(STAGES):
            cell_status = st.grid[st.cur_scene][i]
            icon, fg, bg = styles[cell_status]
            border = s["primary"] if (i == st.cur_stage and active) else "transparent"
            self._stepper[i].setText(f"{icon}\n{t(key)}")
            self._stepper[i].setStyleSheet(
                f"background:{bg}; color:{fg}; border-radius:10px; border:2px solid {border};"
                " font-size:12px; font-weight:700; padding:4px;"
            )
        self.detail_caption.setText(t("sd.detail.caption", scene=st.cur_scene + 1))

        # timeline grid
        self.tracker.update_grid(st, self._dark)

        # mode buttons
        locked = self._locked()
        for btn, mode in ((self.auto_btn, "auto"), (self.manual_btn, "manual")):
            btn.setProperty("variant", "primary" if st.mode == mode else "")
            btn.setEnabled(not locked)
            repolish(btn)
        for sid, cb in self._skip_checks.items():
            cb.setEnabled(not locked)
            cb.blockSignals(True)
            cb.setChecked(self.state.stage_skip[sid])
            cb.blockSignals(False)

        # manual-override persistence state
        skipped = [t(key) for sid, key in STAGES if st.stage_skip[sid]]
        overrides = []
        if st.mode == "manual":
            overrides.append(t("sd.persist.mode_manual"))
        if skipped:
            overrides.append(t("sd.persist.skip", stages=", ".join(skipped)))
        if overrides:
            self.persist_note.setText(t("sd.persist.active", details=" · ".join(overrides)))
            self.persist_note.setStyleSheet(f"color:{s['info_fg']}; font-weight:600;")
        else:
            self.persist_note.setText(t("sd.persist.none"))
            self.persist_note.setStyleSheet(f"color:{s['ink_faint']};")

        self._render_actions()

    def _render_actions(self):
        clear_layout(self.actions_container)

        st = self.state.status
        self.actions_prompt.setVisible(st == "failed")

        def add(text_key, handler, primary=False, danger=False):
            btn = QPushButton(t(text_key))
            btn.setCursor(Qt.PointingHandCursor)
            if primary:
                btn.setProperty("variant", "primary")
            elif danger:
                btn.setProperty("variant", "danger")
            btn.clicked.connect(handler)
            self.actions_container.addWidget(btn)
            return btn

        if st == "idle":
            add("sd.btn.start", self._start, primary=True)
        elif st == "running":
            add("sd.btn.pause", self._pause)
            add("sd.btn.cancel", self._cancel, danger=True)
        elif st == "paused":
            add("sd.btn.next", self._next_step, primary=True)
            add("sd.btn.cancel", self._cancel, danger=True)
        elif st == "failed":
            self.actions_prompt.setText(
                t("sd.failed.prompt", scene=FAIL_SCENE_IDX + 1, stage=t(STAGES[FAIL_STAGE_IDX][1]))
            )
            self.actions_prompt.setStyleSheet(f"color:{semantic(self._dark)['danger_fg_strong']}; font-weight:600;")
            add("sd.btn.retry", self._retry, primary=True)
            add("common.btn.skip_step", self._skip_scene)  # standardized skip control (B2)
            add("sd.btn.abort", self._cancel, danger=True)
        elif st == "cancelled":
            add("sd.btn.resume", self._resume, primary=True)
            add("sd.btn.restart", self._restart)
        elif st == "complete":
            add("sd.btn.new_batch", self._restart, primary=True)

    # ------------------------------------------------------------------
    # host hooks
    # ------------------------------------------------------------------
    def _on_language_changed(self, _lang: str):
        self.retranslate()

    def set_dark(self, dark: bool):
        self._dark = dark
        self._render_dynamic()
