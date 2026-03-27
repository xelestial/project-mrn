from __future__ import annotations

import os
import sys


def configure_utf8_io() -> None:
    """Force UTF-8 defaults for process I/O and child-process text I/O."""

    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if not callable(reconfigure):
            continue
        kwargs = {"encoding": "utf-8"}
        if stream_name != "stdin":
            kwargs["errors"] = "replace"
        reconfigure(**kwargs)
