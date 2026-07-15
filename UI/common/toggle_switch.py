"""Custom animated iOS-style toggle switch (QAbstractButton subclass).

Qt's automatic RTL mirroring only reorders layouts/alignment — a widget
that paints itself in paintEvent() is not auto-mirrored, so the knob's
travel direction is flipped manually here based on layoutDirection().
"""

from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton


class ToggleSwitch(QAbstractButton):
    def __init__(self, on_color="#a3620a", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(42, 25)

        self._on_color = QColor(on_color)
        self._off_track = QColor("#d9dcd7")
        self._knob_pos = 0.0  # 0.0 = off, 1.0 = on

        self._anim = QPropertyAnimation(self, b"knobPos", self)
        self._anim.setDuration(220)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.toggled.connect(self._animate_to_state)

    def set_on_color(self, color: str):
        self._on_color = QColor(color)
        self.update()

    def set_off_track_color(self, color: str):
        self._off_track = QColor(color)
        self.update()

    def _animate_to_state(self, checked: bool):
        self._anim.stop()
        self._anim.setStartValue(self._knob_pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def _get_knob_pos(self) -> float:
        return self._knob_pos

    def _set_knob_pos(self, value: float):
        self._knob_pos = value
        self.update()

    knobPos = Property(float, _get_knob_pos, _set_knob_pos)

    def sizeHint(self):
        return self.size()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)

        track_color = self._blend(self._off_track, self._on_color, self._knob_pos)
        if not self.isEnabled():
            track_color.setAlpha(90)
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        if self.hasFocus():
            pen = QPen(self._on_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            focus_rect = rect.adjusted(-2, -2, 2, 2)
            painter.drawRoundedRect(focus_rect, focus_rect.height() / 2, focus_rect.height() / 2)

        knob_d = rect.height() - 4
        travel = rect.width() - knob_d - 4
        if self.layoutDirection() == Qt.RightToLeft:
            x = rect.right() - 2 - knob_d - travel * self._knob_pos
        else:
            x = rect.left() + 2 + travel * self._knob_pos
        y = rect.top() + 2

        knob_color = QColor(255, 255, 255, 140 if not self.isEnabled() else 255)
        painter.setPen(Qt.NoPen)
        painter.setBrush(knob_color)
        painter.drawEllipse(int(x), int(y), knob_d, knob_d)

    @staticmethod
    def _blend(c1: QColor, c2: QColor, t: float) -> QColor:
        r = c1.red() + (c2.red() - c1.red()) * t
        g = c1.green() + (c2.green() - c1.green()) * t
        b = c1.blue() + (c2.blue() - c1.blue()) * t
        return QColor(int(r), int(g), int(b))
