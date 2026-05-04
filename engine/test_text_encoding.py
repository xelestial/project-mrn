from __future__ import annotations

from test_import_bootstrap import bootstrap_local_test_imports

bootstrap_local_test_imports(__file__)


import os

from text_encoding import configure_utf8_io


def test_configure_utf8_io_sets_process_defaults() -> None:
    old_utf8 = os.environ.get("PYTHONUTF8")
    old_io = os.environ.get("PYTHONIOENCODING")
    try:
        os.environ.pop("PYTHONUTF8", None)
        os.environ.pop("PYTHONIOENCODING", None)

        configure_utf8_io()

        assert os.environ["PYTHONUTF8"] == "1"
        assert os.environ["PYTHONIOENCODING"] == "utf-8"
    finally:
        if old_utf8 is None:
            os.environ.pop("PYTHONUTF8", None)
        else:
            os.environ["PYTHONUTF8"] = old_utf8

        if old_io is None:
            os.environ.pop("PYTHONIOENCODING", None)
        else:
            os.environ["PYTHONIOENCODING"] = old_io
