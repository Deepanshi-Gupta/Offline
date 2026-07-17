"""Window-size breakpoint check (task B5).

Constructs every screen in both languages and compares its inner content's
minimum width against the width available at each supported breakpoint
(BREAKPOINT_COMPACT / BREAKPOINT_WIDE in hasaballa_desktop_app.py). A screen
"fits" a breakpoint when its inner minimum width is within the window width
minus the sidebar and content margins; otherwise it would show a horizontal
scrollbar at that size.

Uses static minimumSizeHint rather than a live resize loop on purpose — the
offscreen QPA backend does not reliably reflow a resized-and-cached window,
so a resize loop gives inconsistent results between runs; minimumSizeHint on
a freshly-constructed screen is deterministic.

Run:  QT_QPA_PLATFORM=offscreen python tools/check_breakpoints.py
Exit code is non-zero if any screen exceeds WIDE (a hard regression);
COMPACT-only overflows are reported as warnings.
"""

import importlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QScrollArea  # noqa: E402

import hasaballa_desktop_app as shell  # noqa: E402
from common.i18n import lang_manager  # noqa: E402

CONTENT_MARGINS = 48  # content_lay left+right margins in the shell

SCREENS = [
    ("chat_screen", "ChatScreen"),
    ("image_animation_screen", "ImageAnimationScreen"),
    ("image_generation_screen", "ImageGenerationScreen"),
    ("character_pack_screen", "CharacterPackScreen"),
    ("voice_screen", "VoiceScreen"),
    ("lip_sync_screen", "LipSyncScreen"),
    ("audio_layering_screen", "AudioLayeringScreen"),
    ("smart_director_screen", "SmartDirectorScreen"),
    ("motion_generation_screen", "MotionGenerationScreen"),
    ("subtitles_screen", "SubtitlesScreen"),
    ("export_screen", "ExportScreen"),
    ("settings_screen", "SettingsScreen"),
    ("publishing_screen", "PublishingScreen"),
    ("project_management_screen", "ProjectManagementScreen"),
    ("import_media_screen", "ImportMediaScreen"),
    ("standalone_tools_screen", "StandaloneToolsScreen"),
    ("smart_internet_access_screen", "SmartInternetAccessScreen"),
]


def main() -> int:
    app = QApplication(sys.argv)
    sidebar_w = shell.MainWindow().sidebar.sizeHint().width()

    def avail(bp):
        return bp[0] - sidebar_w - CONTENT_MARGINS

    compact, wide = avail(shell.BREAKPOINT_COMPACT), avail(shell.BREAKPOINT_WIDE)
    print(f"sidebar={sidebar_w}  compact_avail={compact}  wide_avail={wide}")

    over_wide, over_compact = [], []
    for lang in ("ar", "en"):
        lang_manager.set_lang(lang)
        for mod, cls in SCREENS:
            screen = getattr(importlib.import_module("qt_screens." + mod), cls)()
            inner = screen.widget() if isinstance(screen, QScrollArea) and screen.widget() else screen
            mw = inner.minimumSizeHint().width()
            if mw > wide:
                over_wide.append((lang, cls, mw))
            elif mw > compact:
                over_compact.append((lang, cls, mw))

    if over_compact:
        print("\nWARN: exceed COMPACT (ok at WIDE):")
        for lang, cls, mw in over_compact:
            print(f"  [{lang}] {cls} innerMinW={mw}")
    if over_wide:
        print("\nFAIL: exceed WIDE (need responsive reflow):")
        for lang, cls, mw in over_wide:
            print(f"  [{lang}] {cls} innerMinW={mw}")
    print(f"\n{len(SCREENS)} screens x 2 languages checked.")
    return 1 if over_wide else 0


if __name__ == "__main__":
    raise SystemExit(main())
