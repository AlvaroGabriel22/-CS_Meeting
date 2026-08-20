"""Logging setup.

Observability requirement: uploads, parsing, translation, exports, version
creation and deletion must leave a trace — without dumping report content into
the logs.
"""

from __future__ import annotations

import logging
import sys

FORMAT = "%(asctime)s %(levelname)-7s %(name)s | %(message)s"


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    if root.handlers:  # already configured (tests, reload)
        root.setLevel(level)
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(FORMAT))
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("app").setLevel(level)
