"""Explicit frame/module runtime contracts.

The real module runner is introduced in guarded slices.  This package starts
with stable data contracts, validation, and legacy event metadata so the
existing engine can expose its current phase without changing gameplay order.
"""

from .contracts import (
    DomainEvent,
    FrameState,
    GameRuntimeState,
    ModuleError,
    ModuleJournalEntry,
    ModuleRef,
    ModuleResult,
    Modifier,
    ModifierRegistryState,
    PromptContinuation,
    QueueOp,
)

__all__ = [
    "DomainEvent",
    "FrameState",
    "GameRuntimeState",
    "ModuleError",
    "ModuleJournalEntry",
    "ModuleRef",
    "ModuleResult",
    "Modifier",
    "ModifierRegistryState",
    "PromptContinuation",
    "QueueOp",
]
