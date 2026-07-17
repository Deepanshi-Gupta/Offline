"""Build-time feature flags for the Hasaballa AI Platform desktop app.

Some controls exist only to make otherwise-unreachable states testable for
internal QA — a demo toggle to force the publishing screen online without a
real OAuth round-trip, a button to force a token-expiry state, a control to
force the subtitle out-of-sync warning. These must never appear in a build
handed to the client.

`DEV_BUILD` gates them. It is OFF by default (i.e. a client build); QA opts
in per session via an environment variable, so no source edit is needed to
produce either build:

    HASABALLA_DEV=1   -> dev/QA build, demo/simulate controls visible
    (unset / any other value) -> client build, demo controls absent

Usage in a screen:

    from common.build_flags import DEV_BUILD
    ...
    if DEV_BUILD:
        self.demo_btn = QPushButton(...)   # built only in QA builds

Gate BOTH the widget's construction and every later reference to it
(retranslate/render) behind the same check so a client build never touches
an attribute that was never created.
"""

import os

DEV_BUILD = os.environ.get("HASABALLA_DEV") == "1"
