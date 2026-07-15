"""Arabic text shaping helper.

IMPORTANT — read before using this in a new screen: Qt's own text engine
(QLabel, QPushButton, QPainter.drawText, QTextDocument — everything that
goes through QTextLayout) already performs full Unicode BiDi + Arabic
contextual shaping via HarfBuzz. Feeding it *raw* logical-order Arabic
Unicode renders correctly out of the box; you only need to set
`QApplication.setLayoutDirection(Qt.RightToLeft)` (or a widget's
`layoutDirection`) for mirroring/alignment.

Running `arabic_reshaper` + `python-bidi` on top of that and handing the
*pre-shaped, pre-reordered* result to a Qt widget double-processes it —
Qt's engine re-applies BiDi to text that's already been visually reordered,
which garbles it. This was verified empirically (offscreen render
comparison) before writing this module: raw text rendered correctly shaped
and ordered; reshaped+bidi'd text rendered broken.

So: for every QLabel / QPushButton / QLineEdit / any QWidget text in this
app, pass raw Arabic Unicode directly — do NOT call `shape_for_raster()`
on it.

`shape_for_raster()` below exists for the *non-Qt* rendering paths
elsewhere in this platform that do their own low-level glyph painting
without a text-shaping engine — e.g. burning subtitles into exported video
frames with Pillow (§10/§11), or drawing Arabic labels on a matplotlib
chart. Those paths render disconnected, backwards letters unless the text
is pre-shaped, exactly as the original audit doc describes. Use it there,
never in a QWidget.
"""

import arabic_reshaper
from bidi.algorithm import get_display


def shape_for_raster(text: str) -> str:
    """Reshape + BiDi-reorder Arabic text for non-Qt raster pipelines
    (Pillow, matplotlib, raw OpenGL/bitmap glyph drawing). Do not use on
    Qt widget text — see module docstring."""
    return get_display(arabic_reshaper.reshape(text))
