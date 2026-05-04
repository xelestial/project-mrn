"""Native module handlers for the modular runtime runner."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..context import ModuleContext
from ..contracts import ModuleResult

ModuleHandler = Callable[[ModuleContext], ModuleResult]


@dataclass(slots=True)
class ModuleHandlerRegistry:
    _handlers: dict[str, ModuleHandler] = field(default_factory=dict)

    def register(self, module_type: str, handler: ModuleHandler) -> None:
        self._handlers[module_type] = handler

    def resolve(self, module_type: str) -> ModuleHandler | None:
        return self._handlers.get(module_type)

    def has(self, module_type: str) -> bool:
        return module_type in self._handlers


def build_default_handler_registry() -> ModuleHandlerRegistry:
    from .player_turn import handle_player_turn

    registry = ModuleHandlerRegistry()
    registry.register("PlayerTurnModule", handle_player_turn)
    return registry
