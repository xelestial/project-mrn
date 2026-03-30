from __future__ import annotations

import sys
from pathlib import Path


def _ensure_project_root_on_path() -> None:
    root = Path(__file__).resolve().parents[3]
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)


_ensure_project_root_on_path()
