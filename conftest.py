from __future__ import annotations

from pathlib import Path

from test_import_bootstrap import activate_test_root


ROOT_DIR = Path(__file__).resolve().parent
ENGINE_DIR = (ROOT_DIR / "engine").resolve()


def _path_from_hook(obj) -> Path:
    return Path(str(obj)).resolve()


def pytest_pycollect_makemodule(module_path, parent):  # type: ignore[no-untyped-def]
    resolved = _path_from_hook(module_path)
    if resolved.is_relative_to(ENGINE_DIR):
        activate_test_root(ENGINE_DIR)
    return None


def pytest_runtest_setup(item) -> None:  # type: ignore[no-untyped-def]
    resolved = _path_from_hook(getattr(item, "path", ""))
    if resolved.is_relative_to(ENGINE_DIR):
        activate_test_root(ENGINE_DIR)
