from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import DomainEvent, FrameState, Modifier, ModuleRef, QueueOp
from .modifiers import ModifierRegistry


@dataclass(slots=True)
class ModuleContext:
    """Standard handler input for native runtime modules."""

    runner: Any
    engine: Any
    state: Any
    frame: FrameState
    module: ModuleRef
    events: list[DomainEvent] = field(default_factory=list)
    queue_ops: list[QueueOp] = field(default_factory=list)
    modifier_ops: list[dict[str, Any]] = field(default_factory=list)

    @property
    def owner_player_id(self) -> int | None:
        return self.module.owner_player_id if self.module.owner_player_id is not None else self.frame.owner_player_id

    def emit(self, event_type: str, **payload: Any) -> DomainEvent:
        event = DomainEvent(event_type=event_type, payload=dict(payload))
        self.events.append(event)
        return event

    def push_front(self, module: ModuleRef, *, target_frame_id: str | None = None) -> None:
        self.queue_ops.append({"op": "push_front", "target_frame_id": target_frame_id or self.frame.frame_id, "module": module})

    def push_back(self, module: ModuleRef, *, target_frame_id: str | None = None) -> None:
        self.queue_ops.append({"op": "push_back", "target_frame_id": target_frame_id or self.frame.frame_id, "module": module})

    def insert_after(
        self,
        module: ModuleRef,
        *,
        anchor_module_id: str | None = None,
        target_frame_id: str | None = None,
    ) -> None:
        self.queue_ops.append(
            {
                "op": "insert_after",
                "target_frame_id": target_frame_id or self.frame.frame_id,
                "anchor_module_id": anchor_module_id or self.module.module_id,
                "module": module,
            }
        )

    def spawn_child_frame(self, frame: FrameState, *, target_frame_id: str | None = None) -> None:
        self.queue_ops.append({"op": "spawn_child_frame", "target_frame_id": target_frame_id or self.frame.frame_id, "frame": frame})

    def complete_frame(self, *, target_frame_id: str | None = None) -> None:
        self.queue_ops.append({"op": "complete_frame", "target_frame_id": target_frame_id or self.frame.frame_id})

    def add_modifier(self, modifier: Modifier) -> Modifier:
        ModifierRegistry(self.state.runtime_modifier_registry).add(modifier)
        self.modifier_ops.append({"op": "add", "modifier_id": modifier.modifier_id})
        return modifier

    def consume_modifier(self, modifier_id: str) -> Modifier | None:
        modifier = ModifierRegistry(self.state.runtime_modifier_registry).consume(modifier_id)
        if modifier is not None:
            self.modifier_ops.append({"op": "consume", "modifier_id": modifier.modifier_id})
        return modifier

    def applicable_modifiers(self, module_type: str | None = None, owner_player_id: int | None = None) -> list[Modifier]:
        return ModifierRegistry(self.state.runtime_modifier_registry).applicable(
            module_type or self.module.module_type,
            owner_player_id=self.owner_player_id if owner_player_id is None else owner_player_id,
        )
