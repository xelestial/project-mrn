from __future__ import annotations

from pathlib import Path

from test_import_bootstrap import activate_test_root


THIS_DIR = Path(__file__).resolve().parent
SIBLING_DIR = (THIS_DIR.parent / "GPT").resolve()


def _purge_sibling_modules() -> None:
    activate_test_root(THIS_DIR, SIBLING_DIR)


_purge_sibling_modules()


def pytest_collect_file(file_path, parent):  # type: ignore[no-untyped-def]
    _purge_sibling_modules()
    return None


def pytest_runtest_setup(item) -> None:  # type: ignore[no-untyped-def]
    _purge_sibling_modules()
