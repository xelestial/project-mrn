from __future__ import annotations

import sys
from pathlib import Path


def activate_test_root(target_dir: Path) -> None:
    target_text = str(target_dir)
    if target_text in sys.path:
        sys.path.remove(target_text)
    sys.path.insert(0, target_text)


def bootstrap_local_test_imports(test_file: str) -> None:
    this_dir = Path(test_file).resolve().parent
    activate_test_root(this_dir)
