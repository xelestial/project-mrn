from __future__ import annotations

from dataclasses import dataclass

from .contracts import FrameState, ModuleRef, QueueOp


class QueueValidationError(ValueError):
    pass


@dataclass(slots=True)
class FrameQueueApi:
    frames: list[FrameState]

    def apply(self, queue_ops: list[QueueOp]) -> None:
        for op in queue_ops:
            self._apply_one(op)

    def _apply_one(self, op: QueueOp) -> None:
        kind = op["op"]
        frame = self._frame(op["target_frame_id"])
        if frame.status == "completed":
            if kind == "complete_frame":
                return
            raise QueueValidationError(f"completed frame rejects queue op: {frame.frame_id}")
        if frame.status not in {"running", "suspended"}:
            raise QueueValidationError(f"frame is not mutable: {frame.frame_id}")
        if kind == "complete_frame":
            frame.status = "completed"
            frame.active_module_id = None
            return
        if kind == "spawn_child_frame":
            child = op.get("frame")
            if child is None:
                raise QueueValidationError("spawn_child_frame requires frame")
            if child.parent_frame_id != frame.frame_id:
                raise QueueValidationError("child frame parent must equal target frame")
            if frame.active_module_id and child.created_by_module_id not in {None, frame.active_module_id}:
                raise QueueValidationError("child frame creator must be active module")
            self.frames.append(child)
            frame.status = "suspended"
            return
        modules = _op_modules(op)
        for module in modules:
            self._validate_module_for_frame(frame, module)
        existing = {module.module_id: module for module in frame.module_queue}
        for module in modules:
            previous = existing.get(module.module_id)
            if previous is not None and previous.idempotency_key != module.idempotency_key:
                raise QueueValidationError(f"duplicate module_id with different idempotency_key: {module.module_id}")
        if kind == "push_front":
            frame.module_queue[0:0] = modules
            return
        if kind == "push_back":
            frame.module_queue.extend(modules)
            return
        if kind == "replace_current":
            frame.module_queue = modules
            frame.active_module_id = None
            return
        if kind == "insert_after":
            anchor = str(op.get("anchor_module_id") or "")
            for index, module in enumerate(frame.module_queue):
                if module.module_id == anchor:
                    frame.module_queue[index + 1 : index + 1] = modules
                    return
            raise QueueValidationError(f"anchor module not found: {anchor}")
        raise QueueValidationError(f"unsupported queue op: {kind}")

    def _frame(self, frame_id: str) -> FrameState:
        for frame in self.frames:
            if frame.frame_id == frame_id:
                return frame
        raise QueueValidationError(f"frame not found: {frame_id}")

    @staticmethod
    def _validate_module_for_frame(frame: FrameState, module: ModuleRef) -> None:
        if frame.frame_type == "simultaneous":
            allowed = {
                "ResupplyModule",
                "SimultaneousPromptBatchModule",
                "SimultaneousCommitModule",
                "CompleteSimultaneousResolutionModule",
            }
            if module.module_type not in allowed:
                raise QueueValidationError(
                    f"{module.module_type} is not allowed in SimultaneousResolutionFrame"
                )
            return
        if module.module_type == "DraftModule" and frame.frame_type != "round":
            raise QueueValidationError("DraftModule is allowed only in RoundFrame")
        if module.module_type == "RoundEndCardFlipModule" and frame.frame_type != "round":
            raise QueueValidationError("RoundEndCardFlipModule is allowed only in RoundFrame")
        if module.module_type == "TurnEndSnapshotModule" and frame.frame_type != "turn":
            raise QueueValidationError("TurnEndSnapshotModule is allowed only in TurnFrame")


def _op_modules(op: QueueOp) -> list[ModuleRef]:
    if "modules" in op:
        return list(op["modules"])
    if "module" in op:
        return [op["module"]]
    return []
