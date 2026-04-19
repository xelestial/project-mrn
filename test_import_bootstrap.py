from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType


def module_belongs_to_root(module: ModuleType, root_dir: Path) -> bool:
    module_file = getattr(module, "__file__", None)
    if isinstance(module_file, str):
        try:
            return Path(module_file).resolve().is_relative_to(root_dir)
        except OSError:
            return False
    module_path = getattr(module, "__path__", None)
    if module_path is None:
        return False
    try:
        return any(Path(entry).resolve().is_relative_to(root_dir) for entry in module_path)
    except OSError:
        return False


def activate_test_root(target_dir: Path, sibling_dir: Path | None = None) -> None:
    target_text = str(target_dir)
    if target_text in sys.path:
        sys.path.remove(target_text)
    sys.path.insert(0, target_text)

    if sibling_dir is None:
        return
    for name, module in list(sys.modules.items()):
        if isinstance(module, ModuleType) and module_belongs_to_root(module, sibling_dir):
            sys.modules.pop(name, None)


def bootstrap_local_test_imports(test_file: str) -> None:
    this_dir = Path(test_file).resolve().parent
    if this_dir.name not in {"GPT", "CLAUDE"}:
        activate_test_root(this_dir)
        return
    sibling_dir = (this_dir.parent / ("CLAUDE" if this_dir.name == "GPT" else "GPT")).resolve()
    activate_test_root(this_dir, sibling_dir)
