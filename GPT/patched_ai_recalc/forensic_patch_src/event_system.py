from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable, DefaultDict

TraceHook = Callable[[str, tuple[Any, ...], dict[str, Any], list[Any], str], None]

EventHandler = Callable[..., Any]


class EventDispatcher:
    """Small synchronous event bus for in-process game effect handling."""

    def __init__(self) -> None:
        self._handlers: DefaultDict[str, list[EventHandler]] = defaultdict(list)
        self._trace_hook: TraceHook | None = None

    def set_trace_hook(self, trace_hook: TraceHook | None) -> None:
        self._trace_hook = trace_hook

    def register(self, event_name: str, handler: EventHandler) -> None:
        self._handlers[event_name].append(handler)

    def clear(self, event_name: str) -> None:
        self._handlers[event_name].clear()

    def emit(self, event_name: str, *args: Any, **kwargs: Any) -> list[Any]:
        results = [handler(*args, **kwargs) for handler in self._handlers.get(event_name, [])]
        self._trace(event_name, args, kwargs, results, mode="emit")
        return results

    def emit_first_non_none(self, event_name: str, *args: Any, **kwargs: Any) -> Any:
        results: list[Any] = []
        for handler in self._handlers.get(event_name, []):
            result = handler(*args, **kwargs)
            results.append(result)
            if result is not None:
                self._trace(event_name, args, kwargs, results, mode="emit_first_non_none")
                return result
        self._trace(event_name, args, kwargs, results, mode="emit_first_non_none")
        return None

    def _trace(self, event_name: str, args: tuple[Any, ...], kwargs: dict[str, Any], results: list[Any], mode: str) -> None:
        if self._trace_hook is None:
            return
        self._trace_hook(event_name, args, kwargs, results, mode)

    def registered_event_names(self) -> list[str]:
        return sorted(self._handlers.keys())
