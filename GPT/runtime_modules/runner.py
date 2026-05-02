from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from viewer.events import Phase
from viewer.public_state import build_turn_end_snapshot

from .contracts import FrameState, ModuleJournalEntry, ModuleRef, ModuleResult
from .ids import round_frame_id
from .round_modules import (
    assert_round_end_card_flip_ready,
    build_round_frame,
)
from .sequence_modules import (
    build_action_sequence_frame,
    build_turn_completion_sequence_frame,
)
from .simultaneous import build_resupply_frame


class ModuleRunnerError(RuntimeError):
    pass


@dataclass(slots=True)
class ModuleRunner:
    """Skeleton one-step runner.

    Concrete gameplay modules land in later migration slices.  This runner
    establishes the invariant that only one explicit queued module becomes
    active during an advance.
    """

    def advance_one(self, frame_stack: list[FrameState]) -> ModuleResult | None:
        frame = self._active_frame(frame_stack)
        if frame is None:
            return None
        if not frame.module_queue:
            frame.status = "completed"
            frame.active_module_id = None
            return None
        module = frame.module_queue.pop(0)
        frame.active_module_id = module.module_id
        module.status = "running"
        return ModuleResult(status="completed")

    def advance_engine(self, engine: Any, state: Any) -> dict[str, Any]:
        """Advance one gameplay transition for a module-runner session.

        This migration bridge keeps the existing rule helpers as the source of
        gameplay semantics while persisting explicit round/player-turn module
        progress in the checkpoint. Later slices can replace individual
        adapters with native module handlers without changing backend/frontend
        contracts.
        """
        self._promote_pending_work_to_sequence_frames(engine, state)
        simultaneous_frame = self._active_simultaneous_frame(state)
        if simultaneous_frame is not None:
            result = self._advance_simultaneous_frame(engine, state, simultaneous_frame)
            self._promote_pending_work_to_sequence_frames(engine, state)
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}
        sequence_frame = self._active_sequence_frame(state)
        if sequence_frame is not None:
            result = self._advance_sequence_frame(engine, state, sequence_frame)
            self._promote_pending_work_to_sequence_frames(engine, state)
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}
        if not state.runtime_frame_stack or not state.current_round_order:
            initial_round = (
                state.rounds_completed == 0
                and state.turn_index == 0
                and state.current_weather is None
                and not any(p.turns_taken for p in state.players)
            )
            if not initial_round and engine._check_end(state):
                return {"status": "finished", "reason": "end_rule", "runner_kind": "module"}
            engine._start_new_round(state, initial=initial_round)
            self._install_round_frame_from_state(engine, state, completed_setup=True)
            return {"status": "committed", "runner_kind": "module", "module_type": "TurnSchedulerModule"}

        self._promote_pending_work_to_sequence_frames(engine, state)
        simultaneous_frame = self._active_simultaneous_frame(state)
        if simultaneous_frame is not None:
            result = self._advance_simultaneous_frame(engine, state, simultaneous_frame)
            self._promote_pending_work_to_sequence_frames(engine, state)
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}
        sequence_frame = self._active_sequence_frame(state)
        if sequence_frame is not None:
            result = self._advance_sequence_frame(engine, state, sequence_frame)
            self._promote_pending_work_to_sequence_frames(engine, state)
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}

        frame = self._active_round_frame(state)
        if frame is None:
            self._install_round_frame_from_state(engine, state, completed_setup=True)
            frame = self._active_round_frame(state)
        if frame is None:
            return {"status": "finished", "reason": "empty_round_frame", "runner_kind": "module"}
        module = self._next_live_module(frame)
        if module is None:
            frame.status = "completed"
            return {"status": "committed", "runner_kind": "module", "module_type": "RoundFrameComplete"}
        frame.active_module_id = module.module_id
        module.status = "running"
        if module.module_type == "PlayerTurnModule":
            return self._advance_player_turn_module(engine, state, frame, module)
        if module.module_type == "RoundEndCardFlipModule":
            assert_round_end_card_flip_ready(frame)
            engine._apply_round_end_marker_management(state)
            engine._resolve_marker_flip(state)
            self._complete_module(state, frame, module)
            return {"status": "committed", "runner_kind": "module", "module_type": module.module_type}
        if module.module_type == "RoundCleanupAndNextRoundModule":
            state.rounds_completed += 1
            frame.status = "completed"
            self._complete_module(state, frame, module)
            state.current_round_order = []
            state.runtime_frame_stack = []
            return {"status": "committed", "runner_kind": "module", "module_type": module.module_type}
        self._complete_module(state, frame, module)
        return {"status": "committed", "runner_kind": "module", "module_type": module.module_type}

    @staticmethod
    def _active_frame(frame_stack: list[FrameState]) -> FrameState | None:
        for frame in reversed(frame_stack):
            if frame.status in {"running", "suspended"}:
                return frame
        return None

    @staticmethod
    def _active_round_frame(state: Any) -> FrameState | None:
        expected = round_frame_id(state.rounds_completed + 1)
        for frame in state.runtime_frame_stack:
            if frame.frame_id == expected and frame.frame_type == "round" and frame.status != "completed":
                return frame
        for frame in state.runtime_frame_stack:
            if frame.frame_type == "round" and frame.status != "completed":
                return frame
        return None

    @staticmethod
    def _next_live_module(frame: FrameState) -> ModuleRef | None:
        for module in frame.module_queue:
            if module.status in {"queued", "running", "suspended"}:
                return module
        return None

    def _install_round_frame_from_state(self, engine: Any, state: Any, *, completed_setup: bool) -> None:
        frame = build_round_frame(
            state.rounds_completed + 1,
            session_id=getattr(engine, "_vis_session_id", ""),
            player_order=list(state.current_round_order or []),
            completed_setup=completed_setup,
        )
        state.runtime_runner_kind = "module"
        state.runtime_checkpoint_schema_version = max(int(getattr(state, "runtime_checkpoint_schema_version", 1) or 1), 3)
        state.runtime_frame_stack = [frame]
        if completed_setup:
            for module_id in frame.completed_module_ids:
                state.runtime_module_journal.append(
                    ModuleJournalEntry(
                        module_id=module_id,
                        frame_id=frame.frame_id,
                        status="completed",
                        idempotency_key=module_id,
                    )
                )

    def _advance_player_turn_module(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef) -> dict[str, Any]:
        player_id = int(module.owner_player_id if module.owner_player_id is not None else 0)
        player = state.players[player_id]
        if player.alive:
            player.turns_taken += 1
            engine._take_turn(state, player)
            if state.pending_actions or state.pending_turn_completion:
                self._promote_pending_work_to_sequence_frames(engine, state, parent_frame=frame, parent_module=module)
                module.status = "suspended"
                return {
                    "status": "committed",
                    "runner_kind": "module",
                    "module_type": module.module_type,
                    "player_id": player_id + 1,
                    "pending_actions": len(state.pending_actions),
                    "pending_modules": self._pending_sequence_module_count(state),
                }
            if engine._check_end(state):
                self._complete_module(state, frame, module)
                return {"status": "finished", "reason": "end_rule", "runner_kind": "module", "player_id": player_id + 1}
        else:
            module.status = "skipped"
            self._complete_module(state, frame, module, status="skipped")
            return {"status": "committed", "runner_kind": "module", "player_id": player_id + 1, "skipped": True}
        self._complete_module(state, frame, module)
        state.turn_index += 1
        return {"status": "committed", "runner_kind": "module", "module_type": module.module_type, "player_id": player_id + 1}

    def _advance_sequence_frame(self, engine: Any, state: Any, frame: FrameState) -> dict[str, Any]:
        module = self._next_live_module(frame)
        if module is None:
            frame.status = "completed"
            frame.active_module_id = None
            return {"status": "committed", "module_type": "SequenceFrameComplete", "frame_id": frame.frame_id}
        frame.active_module_id = module.module_id
        module.status = "running"
        if "action" in module.payload:
            return self._advance_action_adapter_module(engine, state, frame, module)
        if "pending_turn_completion" in module.payload:
            return self._advance_turn_completion_module(engine, state, frame, module)
        self._complete_module(state, frame, module)
        return {"status": "committed", "module_type": module.module_type, "frame_id": frame.frame_id}

    def _advance_simultaneous_frame(self, engine: Any, state: Any, frame: FrameState) -> dict[str, Any]:
        module = self._next_live_module(frame)
        if module is None:
            frame.status = "completed"
            frame.active_module_id = None
            return {"status": "committed", "module_type": "SimultaneousFrameComplete", "frame_id": frame.frame_id}
        frame.active_module_id = module.module_id
        module.status = "running"
        if module.module_type == "ResupplyModule":
            action_payload = dict(module.payload.get("action") or {})
            result = (
                engine._execute_action(state, self._action_from_payload(action_payload), queue_followups=True)
                if action_payload
                else {"type": "RESUPPLY_NOOP"}
            )
            self._complete_module(state, frame, module)
            return {
                "status": "committed",
                "module_type": module.module_type,
                "frame_id": frame.frame_id,
                "pending_actions": len(state.pending_actions),
                "pending_modules": self._pending_sequence_module_count(state),
                "result": result,
            }
        self._complete_module(state, frame, module)
        if module.module_type == "CompleteSimultaneousResolutionModule":
            frame.status = "completed"
        return {"status": "committed", "module_type": module.module_type, "frame_id": frame.frame_id}

    def _advance_action_adapter_module(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef) -> dict[str, Any]:
        action = self._action_from_payload(dict(module.payload.get("action") or {}))
        try:
            result = engine._execute_action(state, action, queue_followups=True)
        except Exception:
            module.status = "suspended"
            frame.status = "suspended"
            raise
        self._complete_module(state, frame, module)
        self._complete_sequence_frame_if_drained(frame)
        engine._log(
            {
                "event": "action_transition",
                "action_id": action.action_id,
                "action_type": action.type,
                "actor_player_id": action.actor_player_id + 1,
                "source": action.source,
                "result": result,
                "pending_actions": len(state.pending_actions),
                "module_id": module.module_id,
                "frame_id": frame.frame_id,
            }
        )
        return {
            "status": "committed",
            "module_type": module.module_type,
            "action_id": action.action_id,
            "action_type": action.type,
            "player_id": action.actor_player_id + 1,
            "turn_index": state.turn_index,
            "pending_actions": len(state.pending_actions),
            "pending_modules": self._pending_sequence_module_count(state),
        }

    def _advance_turn_completion_module(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef) -> dict[str, Any]:
        original_pending = dict(state.pending_turn_completion or {})
        state.pending_turn_completion = dict(module.payload.get("pending_turn_completion") or {})
        try:
            result = self._complete_pending_turn_transition(engine, state)
        except Exception:
            module.status = "suspended"
            frame.status = "suspended"
            state.pending_turn_completion = original_pending or state.pending_turn_completion
            raise
        self._complete_module(state, frame, module)
        self._complete_sequence_frame_if_drained(frame)
        return {**result, "module_type": module.module_type, "frame_id": frame.frame_id}

    @staticmethod
    def _complete_pending_turn_transition(engine: Any, state: Any) -> dict[str, Any]:
        """Complete a suspended turn without running legacy round-end advance.

        The legacy helper intentionally rolls turn completion, card-flip, round
        cleanup, and next-round setup into one transition. Module-runner
        sessions keep those as explicit queued modules, so only the turn-end
        snapshot and turn cursor advance belong here.
        """
        pending = dict(state.pending_turn_completion)
        state.pending_turn_completion = {}
        player_id = int(pending.get("player_id", 0) or 0)
        player = state.players[player_id]
        disruption_before = dict(pending.get("disruption_before") or {})
        disruption_after = engine._leader_disruption_snapshot(state, player)
        finisher_before = int(pending.get("finisher_before", 0) or 0)
        awarded = engine._maybe_award_control_finisher_window(state, player, disruption_before, disruption_after)
        if finisher_before > 0 and not awarded:
            player.control_finisher_turns = max(0, finisher_before - 1)
            if player.control_finisher_turns == 0:
                player.control_finisher_reason = ""
        engine._emit_vis(
            "turn_end_snapshot",
            Phase.TURN_END,
            player.player_id + 1,
            state,
            snapshot=build_turn_end_snapshot(state),
        )
        if engine._check_end(state):
            return {"status": "finished", "reason": "end_rule", "player_id": player_id + 1}
        state.turn_index += 1
        return {"status": "committed", "player_id": player_id + 1, "turn_index": state.turn_index}

    def _sync_active_player_turn_after_legacy_work(self, state: Any) -> None:
        if state.pending_actions or state.pending_turn_completion or self._active_sequence_frame(state) is not None:
            return
        frame = self._active_round_frame(state)
        if frame is None:
            return
        for module in frame.module_queue:
            if module.module_type == "PlayerTurnModule" and module.status == "suspended":
                self._complete_module(state, frame, module)
                return

    def _promote_pending_work_to_sequence_frames(
        self,
        engine: Any,
        state: Any,
        *,
        parent_frame: FrameState | None = None,
        parent_module: ModuleRef | None = None,
    ) -> None:
        frame = parent_frame or self._active_round_frame(state) or self._active_frame(state.runtime_frame_stack)
        if frame is None:
            return
        module = parent_module or self._next_live_module(frame)
        parent_module_id = module.module_id if module is not None else frame.active_module_id or frame.frame_id
        session_id = getattr(engine, "_vis_session_id", "")
        round_index = int(getattr(state, "rounds_completed", 0) or 0) + 1
        if state.pending_turn_completion:
            pending = dict(state.pending_turn_completion)
            state.pending_turn_completion = {}
            state.runtime_frame_stack.append(
                build_turn_completion_sequence_frame(
                    round_index,
                    self._optional_int(pending.get("player_id")),
                    self._next_sequence_ordinal(state),
                    pending,
                    parent_frame_id=frame.frame_id,
                    parent_module_id=parent_module_id,
                    session_id=session_id,
                )
            )
        if state.pending_actions:
            supply_actions, actions = self._split_supply_threshold_actions(
                [action.to_payload() for action in state.pending_actions]
            )
            state.pending_actions = []
            for action in supply_actions:
                ordinal = self._next_simultaneous_ordinal(state)
                resupply_frame = build_resupply_frame(
                    round_index,
                    ordinal,
                    parent_frame_id=frame.frame_id,
                    parent_module_id=parent_module_id,
                    session_id=session_id,
                    participants=self._resupply_participants(state, action),
                )
                resupply_frame.module_queue[0].payload["action"] = dict(action)
                state.runtime_frame_stack.append(resupply_frame)
            if not actions:
                return
            owner = self._sequence_owner(actions, getattr(frame, "owner_player_id", None))
            state.runtime_frame_stack.append(
                build_action_sequence_frame(
                    round_index,
                    owner,
                    self._next_sequence_ordinal(state),
                    actions,
                    parent_frame_id=frame.frame_id,
                    parent_module_id=parent_module_id,
                    session_id=session_id,
                )
            )

    @staticmethod
    def _action_from_payload(payload: dict[str, Any]) -> Any:
        from state import ActionEnvelope

        return ActionEnvelope.from_payload(payload)

    @staticmethod
    def _complete_sequence_frame_if_drained(frame: FrameState) -> None:
        if all(module.status in {"completed", "skipped"} for module in frame.module_queue):
            frame.status = "completed"
            frame.active_module_id = None

    @staticmethod
    def _active_sequence_frame(state: Any) -> FrameState | None:
        for frame in reversed(state.runtime_frame_stack):
            if frame.frame_type == "sequence" and frame.status in {"running", "suspended"}:
                return frame
        return None

    @staticmethod
    def _active_simultaneous_frame(state: Any) -> FrameState | None:
        for frame in reversed(state.runtime_frame_stack):
            if frame.frame_type == "simultaneous" and frame.status in {"running", "suspended"}:
                return frame
        return None

    @staticmethod
    def _split_supply_threshold_actions(actions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        supply_actions: list[dict[str, Any]] = []
        remaining_actions: list[dict[str, Any]] = []
        for action in actions:
            if action.get("type") == "resolve_supply_threshold":
                supply_actions.append(action)
            else:
                remaining_actions.append(action)
        return supply_actions, remaining_actions

    @staticmethod
    def _resupply_participants(state: Any, action: dict[str, Any]) -> list[int]:
        payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
        raw_participants = payload.get("participants") if isinstance(payload, dict) else None
        if isinstance(raw_participants, list):
            participants: list[int] = []
            for item in raw_participants:
                try:
                    participants.append(int(item))
                except (TypeError, ValueError):
                    continue
            return participants
        return [
            int(getattr(player, "player_id"))
            for player in getattr(state, "players", [])
            if getattr(player, "alive", True)
        ]

    @staticmethod
    def _next_sequence_ordinal(state: Any) -> int:
        existing = [frame for frame in state.runtime_frame_stack if frame.frame_type == "sequence"]
        return len(existing) + len(getattr(state, "runtime_module_journal", [])) + 1

    @staticmethod
    def _next_simultaneous_ordinal(state: Any) -> int:
        existing = [frame for frame in state.runtime_frame_stack if frame.frame_type == "simultaneous"]
        return len(existing) + len(getattr(state, "runtime_module_journal", [])) + 1

    @staticmethod
    def _sequence_owner(actions: list[dict[str, Any]], fallback: int | None) -> int | None:
        if not actions:
            return fallback
        actor_ids = {ModuleRunner._optional_int(action.get("actor_player_id")) for action in actions}
        actor_ids.discard(None)
        return next(iter(actor_ids)) if len(actor_ids) == 1 else fallback

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _pending_sequence_module_count(state: Any) -> int:
        return sum(
            1
            for frame in state.runtime_frame_stack
            if frame.frame_type == "sequence" and frame.status != "completed"
            for module in frame.module_queue
            if module.status in {"queued", "running", "suspended"}
        )

    @staticmethod
    def _complete_module(state: Any, frame: FrameState, module: ModuleRef, *, status: str = "completed") -> None:
        module.status = status  # type: ignore[assignment]
        frame.active_module_id = None
        if module.module_id not in frame.completed_module_ids:
            frame.completed_module_ids.append(module.module_id)
        state.runtime_module_journal.append(
            ModuleJournalEntry(
                module_id=module.module_id,
                frame_id=frame.frame_id,
                status=module.status,
                idempotency_key=module.idempotency_key,
            )
        )
