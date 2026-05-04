from __future__ import annotations

import sys
from pathlib import Path


_ENGINE_DIR = Path(__file__).resolve().parent
_ENGINE_PATH = str(_ENGINE_DIR)
if _ENGINE_PATH not in sys.path:
    sys.path.insert(0, _ENGINE_PATH)

from .engine import DecisionRequest, GameEngine, GameResult


__all__ = ["DecisionRequest", "GameEngine", "GameResult"]
