"""game_enums — compatibility shim.

Some paths expect `game_enums.CellKind`. CellKind lives in config.py.
This module re-exports it for backward compatibility.
"""
from config import CellKind

__all__ = ["CellKind"]
