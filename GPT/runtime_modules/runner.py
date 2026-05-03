from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import FrameState, ModuleJournalEntry, ModuleRef, ModuleResult
from .handlers.round import ROUND_FRAME_HANDLERS, RoundFrameHandlerContext
from .handlers.sequence import SEQUENCE_FRAME_HANDLERS, SequenceFrameHandlerContext
from .handlers.simultaneous import SIMULTANEOUS_FRAME_HANDLERS, SimultaneousFrameHandlerContext
from .handlers.turn import TURN_FRAME_HANDLERS, TurnFrameHandlerContext
from .ids import round_frame_id
from .modifiers import ModifierRegistry
from .prompts import PromptApi
from .round_modules import build_round_frame
from .sequence_modules import UnknownActionTypeError, build_action_sequence_frame, module_type_for_action
from .simultaneous import build_resupply_frame
from .turn_modules import build_turn_frame

TURN_COMPLETION_FIELD = "pending_turn_completion"


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

    def advance_engine(self, engine: Any, state: Any, decision_resume: Any | None = None) -> dict[str, Any]:
        """Advance one gameplay transition for a module-runner session.

        This migration bridge keeps the existing rule helpers as the source of
        gameplay semantics while persisting explicit round/player-turn module
        progress in the checkpoint. Later slices can replace individual
        adapters with native module handlers without changing backend/frontend
        contracts.
        """
        self._reject_orphan_turn_completion_checkpoint(state)
        self._promote_pending_work_to_sequence_frames(engine, state)
        simultaneous_frame = self._active_simultaneous_frame(state)
        if simultaneous_frame is not None:
            simultaneous_module = self._next_live_module(simultaneous_frame)
            result = self._advance_simultaneous_frame(engine, state, simultaneous_frame, decision_resume=decision_resume)
            self._promote_pending_work_to_sequence_frames(
                engine,
                state,
                parent_frame=simultaneous_frame,
                parent_module=simultaneous_module,
            )
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}
        sequence_frame = self._active_sequence_frame(state)
        if sequence_frame is not None:
            sequence_module = self._next_live_module(sequence_frame)
            result = self._advance_sequence_frame(engine, state, sequence_frame)
            self._promote_pending_work_to_sequence_frames(
                engine,
                state,
                parent_frame=sequence_frame,
                parent_module=sequence_module,
            )
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}
        turn_frame = self._active_turn_frame(state)
        if turn_frame is not None:
            turn_module = self._next_live_module(turn_frame)
            result = self._advance_turn_frame(engine, state, turn_frame)
            self._promote_pending_work_to_sequence_frames(
                engine,
                state,
                parent_frame=turn_frame,
                parent_module=turn_module,
            )
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

        self._reject_orphan_turn_completion_checkpoint(state)
        self._promote_pending_work_to_sequence_frames(engine, state)
        simultaneous_frame = self._active_simultaneous_frame(state)
        if simultaneous_frame is not None:
            simultaneous_module = self._next_live_module(simultaneous_frame)
            result = self._advance_simultaneous_frame(engine, state, simultaneous_frame, decision_resume=decision_resume)
            self._promote_pending_work_to_sequence_frames(
                engine,
                state,
                parent_frame=simultaneous_frame,
                parent_module=simultaneous_module,
            )
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}
        sequence_frame = self._active_sequence_frame(state)
        if sequence_frame is not None:
            sequence_module = self._next_live_module(sequence_frame)
            result = self._advance_sequence_frame(engine, state, sequence_frame)
            self._promote_pending_work_to_sequence_frames(
                engine,
                state,
                parent_frame=sequence_frame,
                parent_module=sequence_module,
            )
            self._sync_active_player_turn_after_legacy_work(state)
            return {**result, "runner_kind": "module"}
        turn_frame = self._active_turn_frame(state)
        if turn_frame is not None:
            turn_module = self._next_live_module(turn_frame)
            result = self._advance_turn_frame(engine, state, turn_frame)
            self._promote_pending_work_to_sequence_frames(
                engine,
                state,
                parent_frame=turn_frame,
                parent_module=turn_module,
            )
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
        handler = ROUND_FRAME_HANDLERS.get(module.module_type)
        if handler is None:
            raise ModuleRunnerError(f"no round handler for module type: {module.module_type}")
        result = handler(RoundFrameHandlerContext(self, engine, state, frame, module))
        return {**result, "runner_kind": "module"}

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

    @staticmethod
    def _reject_orphan_turn_completion_checkpoint(state: Any) -> None:
        if getattr(state, TURN_COMPLETION_FIELD, None):
            raise ModuleRunnerError(
                "pending_turn_completion must be owned by TurnEndSnapshotModule in the active TurnFrame"
            )

    def _advance_player_turn_module(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef) -> dict[str, Any]:
        player_id = int(module.owner_player_id if module.owner_player_id is not None else 0)
        player = state.players[player_id]
        if player.alive:
            existing = self._turn_frame_for_player_module(state, module)
            if existing is None:
                turn_frame = build_turn_frame(
                    int(getattr(state, "rounds_completed", 0) or 0) + 1,
                    player_id,
                    parent_module_id=module.module_id,
                    session_id=getattr(engine, "_vis_session_id", ""),
                )
                state.runtime_frame_stack.append(
                    turn_frame
                )
                module.suspension_id = turn_frame.frame_id
            module.status = "suspended"
            module.cursor = "child_turn_running"
            return {
                "status": "committed",
                "runner_kind": "module",
                "module_type": module.module_type,
                "player_id": player_id + 1,
            }
        else:
            module.status = "skipped"
            self._complete_module(state, frame, module, status="skipped")
            state.turn_index += 1
            return {"status": "committed", "runner_kind": "module", "player_id": player_id + 1, "skipped": True}

    def _advance_turn_frame(self, engine: Any, state: Any, frame: FrameState) -> dict[str, Any]:
        module = self._next_live_module(frame)
        if module is None:
            self._complete_turn_frame_and_parent(state, frame)
            return {"status": "committed", "module_type": "TurnFrameComplete", "frame_id": frame.frame_id}
        player_id = int(frame.owner_player_id if frame.owner_player_id is not None else 0)
        player = state.players[player_id]
        frame.status = "running"
        frame.active_module_id = module.module_id
        module.status = "running"
        self._attach_applicable_modifiers(state, module)
        handler = TURN_FRAME_HANDLERS.get(module.module_type)
        if handler is not None:
            return handler(
                TurnFrameHandlerContext(
                    runner=self,
                    engine=engine,
                    state=state,
                    frame=frame,
                    module=module,
                    player_id=player_id,
                    player=player,
                )
            )
        self._complete_module(state, frame, module)
        return {"status": "committed", "module_type": module.module_type, "player_id": player_id + 1}

    def _advance_sequence_frame(self, engine: Any, state: Any, frame: FrameState) -> dict[str, Any]:
        module = self._next_live_module(frame)
        if module is None:
            frame.status = "completed"
            frame.active_module_id = None
            return {"status": "committed", "module_type": "SequenceFrameComplete", "frame_id": frame.frame_id}
        frame.active_module_id = module.module_id
        module.status = "running"
        self._attach_applicable_modifiers(state, module)
        context = SequenceFrameHandlerContext(
            runner=self,
            engine=engine,
            state=state,
            frame=frame,
            module=module,
        )
        handler = SEQUENCE_FRAME_HANDLERS.get(module.module_type)
        if handler is not None:
            return handler(context)
        if module.module_type == "LegacyActionAdapterModule":
            raise ModuleRunnerError("LegacyActionAdapterModule is no longer executable; catalogue the action module")
        if "action" in module.payload:
            action = module.payload.get("action")
            action_type = action.get("type") if isinstance(action, dict) else None
            raise ModuleRunnerError(
                f"action payload requires a native sequence handler for {module.module_type}: {action_type}"
            )
        self._complete_module(state, frame, module)
        self._complete_sequence_frame_if_drained(frame)
        return {"status": "committed", "module_type": module.module_type, "frame_id": frame.frame_id}

    def _advance_trick_sequence_module(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef) -> dict[str, Any]:
        player_id = int(frame.owner_player_id if frame.owner_player_id is not None else 0)
        player = state.players[player_id]
        if module.module_type == "TrickChoiceModule":
            module.cursor = "await_trick_prompt"
            try:
                deferred = engine._use_trick_phase(
                    state,
                    player,
                    turn_continuation=dict(module.payload.get("turn_context") or {}),
                )
            except Exception:
                module.status = "suspended"
                module.suspension_id = frame.frame_id
                frame.status = "suspended"
                raise
            module.payload["deferred_followups"] = bool(deferred)
            self._copy_last_trick_result_to_resolve_module(state, frame, module, deferred=bool(deferred))
            self._complete_module(state, frame, module)
            self._complete_sequence_frame_if_drained(frame)
            return {
                "status": "committed",
                "module_type": module.module_type,
                "frame_id": frame.frame_id,
                "player_id": player_id + 1,
                "pending_actions": len(state.pending_actions),
                "pending_modules": self._pending_sequence_module_count(state),
            }
        if module.module_type == "TrickResolveModule":
            if self._trick_followup_requested(module):
                self._insert_followup_trick_choice(frame, module)
            self._complete_module(state, frame, module)
            self._complete_sequence_frame_if_drained(frame)
            return {"status": "committed", "module_type": module.module_type, "frame_id": frame.frame_id}
        self._complete_module(state, frame, module)
        self._complete_sequence_frame_if_drained(frame)
        return {"status": "committed", "module_type": module.module_type, "frame_id": frame.frame_id}

    def _advance_simultaneous_frame(
        self,
        engine: Any,
        state: Any,
        frame: FrameState,
        *,
        decision_resume: Any | None = None,
    ) -> dict[str, Any]:
        module = self._next_live_module(frame)
        if module is None:
            frame.status = "completed"
            frame.active_module_id = None
            return {"status": "committed", "module_type": "SimultaneousFrameComplete", "frame_id": frame.frame_id}
        frame.active_module_id = module.module_id
        module.status = "running"
        handler = SIMULTANEOUS_FRAME_HANDLERS.get(module.module_type)
        if handler is not None:
            return handler(
                SimultaneousFrameHandlerContext(
                    runner=self,
                    engine=engine,
                    state=state,
                    frame=frame,
                    module=module,
                    decision_resume=decision_resume,
                )
            )
        self._complete_module(state, frame, module)
        return {"status": "committed", "module_type": module.module_type, "frame_id": frame.frame_id}

    def _advance_resupply_module(
        self,
        engine: Any,
        state: Any,
        frame: FrameState,
        module: ModuleRef,
        *,
        decision_resume: Any | None = None,
    ) -> dict[str, Any]:
        self._ensure_resupply_state(engine, state, module)
        active_batch = getattr(state, "runtime_active_prompt_batch", None)
        if decision_resume is not None:
            if active_batch is None or getattr(active_batch, "module_id", "") != module.module_id:
                raise ModuleRunnerError("resupply decision resume without active batch")
            PromptApi().record_batch_response(
                active_batch,
                player_id=max(0, int(getattr(decision_resume, "player_id", 0) or 0) - 1),
                request_id=str(getattr(decision_resume, "request_id", "") or ""),
                resume_token=str(getattr(decision_resume, "resume_token", "") or ""),
                choice_id=str(getattr(decision_resume, "choice_id", "") or ""),
                response={"choice_payload": dict(getattr(decision_resume, "choice_payload", {}) or {})},
            )
            if active_batch.missing_player_ids:
                return self._resupply_waiting_result(state, frame, module, active_batch)
            self._commit_resupply_batch(engine, state, module, active_batch)
            state.runtime_active_prompt_batch = None

        active_batch = getattr(state, "runtime_active_prompt_batch", None)
        if active_batch is not None and getattr(active_batch, "module_id", "") == module.module_id:
            return self._resupply_waiting_result(state, frame, module, active_batch)

        while True:
            batch = self._build_next_resupply_batch(engine, state, frame, module)
            if batch is None:
                result = self._complete_resupply_module(engine, state, frame, module)
                return result
            if not batch.missing_player_ids:
                self._commit_resupply_batch(engine, state, module, batch)
                continue
            state.runtime_active_prompt = None
            state.runtime_active_prompt_batch = batch
            return self._resupply_waiting_result(state, frame, module, batch)

    def _ensure_resupply_state(self, engine: Any, state: Any, module: ModuleRef) -> dict[str, Any]:
        existing = module.payload.get("resupply_state")
        if isinstance(existing, dict) and existing.get("initialized"):
            return existing
        action_payload = dict(module.payload.get("action") or {})
        action_inner = action_payload.get("payload") if isinstance(action_payload.get("payload"), dict) else {}
        threshold = int((action_inner or {}).get("threshold", action_payload.get("threshold", 0)) or 0)
        participants = [
            int(player_id)
            for player_id in module.payload.get("participants", [])
            if isinstance(player_id, int) or str(player_id).lstrip("-").isdigit()
        ]
        if not participants:
            participants = [int(getattr(player, "player_id")) for player in getattr(state, "players", []) if getattr(player, "alive", True)]
        supplied_eligible_by_player = self._resupply_int_list_by_player(
            self._first_mapping_from_payloads(
                "eligible_burden_deck_indices_by_player",
                action_inner,
                action_payload,
            )
        )
        supplied_processed_by_player = self._resupply_int_list_by_player(
            self._first_mapping_from_payloads(
                "processed_burden_deck_indices_by_player",
                action_inner,
                action_payload,
            )
        )
        eligible_by_player: dict[str, list[int]] = {}
        for player_id in participants:
            player_key = str(player_id)
            if player_key in supplied_eligible_by_player:
                eligible_by_player[player_key] = supplied_eligible_by_player[player_key]
                continue
            player = state.players[player_id]
            eligible_by_player[player_key] = [
                int(getattr(card, "deck_index"))
                for card in getattr(player, "trick_hand", [])
                if getattr(card, "is_burden", False) and isinstance(getattr(card, "deck_index", None), int)
            ]
        resupply_state = {
            "initialized": True,
            "threshold": threshold,
            "participants": participants,
            "eligible_burden_deck_indices_by_player": eligible_by_player,
            "processed_burden_deck_indices_by_player": supplied_processed_by_player,
            "exchanged_by_player": {},
            "batch_ordinal": 0,
            "current_batch_targets_by_player": {},
        }
        module.payload["resupply_state"] = resupply_state
        engine._log(
            {
                "event": "module_resupply_initialized",
                "threshold": threshold,
                "participants": [player_id + 1 for player_id in participants],
                "eligible_burden_deck_indices_by_player": eligible_by_player,
                "module_id": module.module_id,
            }
        )
        return resupply_state

    @staticmethod
    def _first_mapping_from_payloads(key: str, *payloads: Any) -> Any:
        for payload in payloads:
            if isinstance(payload, dict) and isinstance(payload.get(key), dict):
                return payload[key]
        return {}

    @staticmethod
    def _resupply_int_list_by_player(raw: Any) -> dict[str, list[int]]:
        if not isinstance(raw, dict):
            return {}
        result: dict[str, list[int]] = {}
        for player_id, values in raw.items():
            if not isinstance(values, list):
                continue
            seen: set[int] = set()
            converted: list[int] = []
            for value in values:
                try:
                    deck_index = int(value)
                except (TypeError, ValueError):
                    continue
                if deck_index in seen:
                    continue
                seen.add(deck_index)
                converted.append(deck_index)
            result[str(player_id)] = converted
        return result

    def _build_next_resupply_batch(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef):
        resupply_state = self._ensure_resupply_state(engine, state, module)
        participants = [int(player_id) for player_id in resupply_state.get("participants", [])]
        targets: dict[int, Any] = {}
        for player_id in participants:
            player = state.players[player_id]
            if not getattr(player, "alive", True):
                continue
            eligible = {
                int(item)
                for item in resupply_state.get("eligible_burden_deck_indices_by_player", {}).get(str(player_id), [])
                if isinstance(item, int)
            }
            processed = {
                int(item)
                for item in resupply_state.get("processed_burden_deck_indices_by_player", {}).get(str(player_id), [])
                if isinstance(item, int)
            }
            for card in list(getattr(player, "trick_hand", [])):
                deck_index = getattr(card, "deck_index", None)
                if (
                    getattr(card, "is_burden", False)
                    and isinstance(deck_index, int)
                    and deck_index in eligible
                    and deck_index not in processed
                ):
                    targets[player_id] = card
                    break
        if not targets:
            resupply_state["current_batch_targets_by_player"] = {}
            return None

        ordinal = int(resupply_state.get("batch_ordinal", 0) or 0) + 1
        resupply_state["batch_ordinal"] = ordinal
        resupply_state["current_batch_targets_by_player"] = {
            str(player_id): int(getattr(card, "deck_index"))
            for player_id, card in targets.items()
        }
        module.cursor = f"await_resupply_batch:{ordinal}"
        module.suspension_id = frame.frame_id
        frame.status = "suspended"
        module.status = "suspended"
        batch_id = f"batch:{frame.frame_id}:{module.module_id}:{ordinal}"
        legal_choices_by_player_id = {
            player_id: self._burden_exchange_choices(card)
            for player_id, card in targets.items()
        }
        public_context_by_player_id = {
            player_id: self._burden_exchange_context(state, state.players[player_id], card, resupply_state)
            for player_id, card in targets.items()
        }
        batch = PromptApi().create_batch(
            batch_id=batch_id,
            frame=frame,
            module=module,
            participant_player_ids=sorted(targets),
            request_type="burden_exchange",
            legal_choices_by_player_id=legal_choices_by_player_id,
            public_context_by_player_id=public_context_by_player_id,
            eligibility_snapshot={
                "threshold": resupply_state.get("threshold"),
                "targets_by_player": dict(resupply_state["current_batch_targets_by_player"]),
                "eligible_burden_deck_indices_by_player": dict(
                    resupply_state.get("eligible_burden_deck_indices_by_player", {})
                ),
            },
        )
        self._prefill_non_human_resupply_responses(engine, state, batch, targets)
        return batch

    @staticmethod
    def _burden_exchange_choices(card: Any) -> list[dict[str, Any]]:
        cost = int(getattr(card, "burden_cost", 0) or 0)
        name = str(getattr(card, "name", "Burden") or "Burden")
        return [
            {"choice_id": "yes", "title": f"Pay {cost} to remove", "value": {"burden_cost": cost, "card_name": name}},
            {"choice_id": "no", "title": "Keep burden", "value": {"burden_cost": cost, "card_name": name}},
        ]

    @staticmethod
    def _burden_exchange_context(state: Any, player: Any, card: Any, resupply_state: dict[str, Any]) -> dict[str, Any]:
        burden_cards = [
            hand_card
            for hand_card in list(getattr(player, "trick_hand", []) or [])
            if bool(getattr(hand_card, "is_burden", False))
        ]
        return {
            "card_name": getattr(card, "name", None),
            "card_description": getattr(card, "description", None),
            "card_deck_index": getattr(card, "deck_index", None),
            "burden_cost": getattr(card, "burden_cost", None),
            "player_cash": getattr(player, "cash", None),
            "player_position": getattr(player, "position", None),
            "player_hand_coins": getattr(player, "hand_coins", None),
            "player_shards": getattr(player, "shards", None),
            "burden_card_count": len(burden_cards),
            "burden_cards": [
                {
                    "deck_index": getattr(hand_card, "deck_index", None),
                    "name": getattr(hand_card, "name", None),
                    "card_description": getattr(hand_card, "description", None),
                    "burden_cost": getattr(hand_card, "burden_cost", None),
                    "is_current_target": getattr(hand_card, "deck_index", None) == getattr(card, "deck_index", None),
                }
                for hand_card in burden_cards
            ],
            "decision_phase": "trick_supply",
            "decision_reason": "supply_threshold",
            "supply_threshold": resupply_state.get("threshold"),
            "current_f_value": getattr(state, "f_value", None),
        }

    def _prefill_non_human_resupply_responses(self, engine: Any, state: Any, batch: Any, targets: dict[int, Any]) -> None:
        human_seats = getattr(getattr(engine, "policy", None), "_human_seats", None)
        if human_seats is None:
            return
        human_ids = {int(player_id) for player_id in human_seats}
        api = PromptApi()
        for player_id, card in targets.items():
            if player_id in human_ids:
                continue
            prompt = batch.prompts_by_player_id[player_id]
            choice_id = "yes" if getattr(state.players[player_id], "cash", 0) >= getattr(card, "burden_cost", 0) else "no"
            api.record_batch_response(
                batch,
                player_id=player_id,
                request_id=prompt.request_id,
                resume_token=prompt.resume_token,
                choice_id=choice_id,
                response={"provider": "ai_fallback"},
            )

    def _commit_resupply_batch(self, engine: Any, state: Any, module: ModuleRef, batch: Any) -> None:
        resupply_state = self._ensure_resupply_state(engine, state, module)
        targets = {
            int(player_id): int(deck_index)
            for player_id, deck_index in dict(resupply_state.get("current_batch_targets_by_player") or {}).items()
        }
        processed_by_player = resupply_state.setdefault("processed_burden_deck_indices_by_player", {})
        exchanged_by_player = resupply_state.setdefault("exchanged_by_player", {})
        for player_id in sorted(targets):
            player = state.players[player_id]
            deck_index = targets[player_id]
            processed = {
                int(item)
                for item in processed_by_player.get(str(player_id), [])
                if isinstance(item, int)
            }
            processed.add(deck_index)
            processed_by_player[str(player_id)] = sorted(processed)
            response = dict(batch.responses_by_player_id.get(player_id, {}))
            accepted = str(response.get("choice_id") or "") == "yes"
            card = next(
                (
                    hand_card
                    for hand_card in list(getattr(player, "trick_hand", []))
                    if getattr(hand_card, "deck_index", None) == deck_index and getattr(hand_card, "is_burden", False)
                ),
                None,
            )
            if not accepted or card is None or getattr(player, "cash", 0) < getattr(card, "burden_cost", 0):
                continue
            player.cash -= int(getattr(card, "burden_cost", 0) or 0)
            engine._discard_trick(state, player, card)
            exchanged_by_player.setdefault(str(player_id), []).append(
                {"name": getattr(card, "name", ""), "cost": int(getattr(card, "burden_cost", 0) or 0)}
            )
            engine._draw_tricks(state, player, 1)
        resupply_state["current_batch_targets_by_player"] = {}

    def _complete_resupply_module(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef) -> dict[str, Any]:
        resupply_state = self._ensure_resupply_state(engine, state, module)
        event = {"event": "trick_supply", "threshold": resupply_state.get("threshold"), "players": []}
        participants = [int(player_id) for player_id in resupply_state.get("participants", [])]
        exchanged_by_player = dict(resupply_state.get("exchanged_by_player") or {})
        for player_id in participants:
            player = state.players[player_id]
            if not getattr(player, "alive", True):
                continue
            before = len(getattr(player, "trick_hand", []))
            engine._draw_tricks(state, player, max(0, 5 - len(getattr(player, "trick_hand", []))))
            event["players"].append(
                {
                    "player": player.player_id + 1,
                    "before": before,
                    "after": len(player.trick_hand),
                    "exchanged": list(exchanged_by_player.get(str(player_id), [])),
                    "hand": [card.name for card in player.trick_hand],
                    "public_hand": player.public_trick_names(),
                    "hidden_trick_count": player.hidden_trick_count(),
                }
            )
        engine._log(event)
        state.runtime_active_prompt_batch = None
        state.runtime_active_prompt = None
        frame.status = "running"
        self._complete_module(state, frame, module)
        return {
            "status": "committed",
            "module_type": module.module_type,
            "frame_id": frame.frame_id,
            "pending_actions": len(state.pending_actions),
            "pending_modules": self._pending_sequence_module_count(state),
            "result": {"type": "SUPPLY_THRESHOLD", "threshold": resupply_state.get("threshold")},
        }

    @staticmethod
    def _resupply_waiting_result(state: Any, frame: FrameState, module: ModuleRef, batch: Any) -> dict[str, Any]:
        module.status = "suspended"
        module.suspension_id = frame.frame_id
        frame.status = "suspended"
        frame.active_module_id = module.module_id
        state.runtime_active_prompt = None
        state.runtime_active_prompt_batch = batch
        return {
            "status": "waiting_input",
            "reason": "prompt_batch_required",
            "request_type": batch.request_type,
            "batch_id": batch.batch_id,
            "missing_player_ids": [player_id + 1 for player_id in batch.missing_player_ids],
            "module_type": module.module_type,
            "module_id": module.module_id,
            "frame_id": frame.frame_id,
            "module_cursor": module.cursor,
        }

    def _advance_action_module(
        self,
        engine: Any,
        state: Any,
        frame: FrameState,
        module: ModuleRef,
        *,
        module_boundary: str,
    ) -> dict[str, Any]:
        self._validate_action_module_contract(module)
        action = self._action_from_payload(dict(module.payload.get("action") or {}))
        module.cursor = "await_action_prompt"
        try:
            result = engine._execute_action(state, action, queue_followups=True)
        except Exception:
            module.status = "suspended"
            module.suspension_id = frame.frame_id
            frame.status = "suspended"
            raise
        self._attach_pending_turn_completion_to_active_turn_end(state)
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
                "module_boundary": module_boundary,
            }
        )
        return {
            "status": "committed",
            "module_type": module.module_type,
            "module_boundary": module_boundary,
            "action_id": action.action_id,
            "action_type": action.type,
            "player_id": action.actor_player_id + 1,
            "turn_index": state.turn_index,
            "pending_actions": len(state.pending_actions),
            "pending_modules": self._pending_sequence_module_count(state),
        }

    def _advance_native_action_module(self, engine: Any, state: Any, frame: FrameState, module: ModuleRef) -> dict[str, Any]:
        return self._advance_action_module(engine, state, frame, module, module_boundary="native")

    @staticmethod
    def _validate_action_module_contract(module: ModuleRef) -> None:
        action = module.payload.get("action")
        if not isinstance(action, dict):
            raise ModuleRunnerError(f"{module.module_type} requires an action payload")
        action_type = str(action.get("type") or "")
        try:
            expected_module_type = module_type_for_action(action_type)
        except UnknownActionTypeError as exc:
            raise ModuleRunnerError(str(exc)) from exc
        if module.module_type != expected_module_type:
            raise ModuleRunnerError(
                f"action type {action_type} belongs to {expected_module_type}, got {module.module_type}"
            )

    def _attach_pending_turn_completion_to_active_turn_end(self, state: Any) -> None:
        pending = dict(getattr(state, TURN_COMPLETION_FIELD, {}) or {})
        if not pending:
            return
        turn_frame = self._active_turn_frame(state)
        if turn_frame is None:
            return
        turn_end_module = next(
            (module for module in turn_frame.module_queue if module.module_type == "TurnEndSnapshotModule"),
            None,
        )
        if turn_end_module is None:
            return
        setattr(state, TURN_COMPLETION_FIELD, {})
        turn_end_module.payload["turn_completion"] = {
            **dict(turn_end_module.payload.get("turn_completion") or {}),
            **pending,
        }

    def _sync_active_player_turn_after_legacy_work(self, state: Any) -> None:
        if state.pending_actions or self._active_sequence_frame(state) is not None:
            return
        turn_frame = self._active_turn_frame(state)
        if turn_frame is not None:
            suspended = next(
                (
                    module
                    for module in turn_frame.module_queue
                    if module.status == "suspended"
                ),
                None,
            )
            if suspended is not None:
                self._complete_module(state, turn_frame, suspended)
            if self._next_live_module(turn_frame) is None:
                self._complete_turn_frame_and_parent(state, turn_frame)
            else:
                turn_frame.status = "running"
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
        frame = (
            parent_frame
            or self._active_simultaneous_frame(state)
            or self._active_sequence_frame(state)
            or self._active_turn_frame(state)
            or self._active_round_frame(state)
            or self._active_frame(state.runtime_frame_stack)
        )
        if frame is None:
            return
        self._reject_orphan_turn_completion_checkpoint(state)
        module = parent_module or self._next_live_module(frame)
        parent_module_id = module.module_id if module is not None else frame.active_module_id or frame.frame_id
        session_id = getattr(engine, "_vis_session_id", "")
        round_index = int(getattr(state, "rounds_completed", 0) or 0) + 1
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
    def _attach_applicable_modifiers(state: Any, module: ModuleRef) -> None:
        registry_state = getattr(state, "runtime_modifier_registry", None)
        if registry_state is None:
            return
        registry = ModifierRegistry(registry_state)
        for modifier in registry.applicable(module.module_type, owner_player_id=module.owner_player_id):
            if modifier.modifier_id not in module.modifiers:
                module.modifiers.append(modifier.modifier_id)

    @staticmethod
    def _copy_last_trick_result_to_resolve_module(
        state: Any,
        frame: FrameState,
        choice_module: ModuleRef,
        *,
        deferred: bool,
    ) -> None:
        trick_result = getattr(state, "runtime_last_trick_sequence_result", None)
        if trick_result is not None:
            try:
                state.runtime_last_trick_sequence_result = None
            except AttributeError:
                pass
        payload = dict(trick_result or {})
        payload["deferred_followups"] = deferred
        payload["turn_context"] = dict(choice_module.payload.get("turn_context") or {})
        for module in frame.module_queue:
            if module.module_type == "TrickResolveModule" and module.status == "queued":
                module.payload.setdefault("trick_result", payload)
                module.payload.setdefault("turn_context", payload["turn_context"])
                module.payload["deferred_followups"] = deferred
                return

    @staticmethod
    def _trick_followup_requested(module: ModuleRef) -> bool:
        if bool(module.payload.get("followup_trick_prompt")):
            return True
        trick_result = module.payload.get("trick_result")
        if not isinstance(trick_result, dict):
            return False
        resolution = trick_result.get("resolution")
        if not isinstance(resolution, dict):
            resolution = {}
        return bool(
            trick_result.get("followup_trick_prompt")
            or trick_result.get("trick_followup")
            or resolution.get("followup_trick_prompt")
            or resolution.get("trick_followup")
        )

    @staticmethod
    def _insert_followup_trick_choice(frame: FrameState, module: ModuleRef) -> None:
        existing_module_id = module.payload.get("followup_choice_module_id")
        if isinstance(existing_module_id, str) and any(
            candidate.module_id == existing_module_id for candidate in frame.module_queue
        ):
            return
        followup_prefix = f"{module.module_id}:followup_choice:"
        existing_followup = next(
            (
                candidate
                for candidate in frame.module_queue
                if candidate.module_type == "TrickChoiceModule"
                and candidate.module_id.startswith(followup_prefix)
            ),
            None,
        )
        if existing_followup is not None:
            module.payload["followup_choice_module_id"] = existing_followup.module_id
            return
        module_index = next(
            (index for index, candidate in enumerate(frame.module_queue) if candidate is module),
            len(frame.module_queue) - 1,
        )
        followup_index = sum(1 for candidate in frame.module_queue if candidate.module_type == "TrickChoiceModule")
        followup = ModuleRef(
            module_id=f"{module.module_id}:followup_choice:{followup_index}",
            module_type="TrickChoiceModule",
            phase="trickchoice",
            owner_player_id=module.owner_player_id,
            payload={"turn_context": dict(module.payload.get("turn_context") or {})},
            idempotency_key=f"{module.idempotency_key}:followup_choice:{followup_index}",
        )
        frame.module_queue.insert(module_index + 1, followup)
        module.payload["followup_choice_module_id"] = followup.module_id

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
    def _active_turn_frame(state: Any) -> FrameState | None:
        for frame in reversed(state.runtime_frame_stack):
            if frame.frame_type == "turn" and frame.status in {"running", "suspended"}:
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
        module.cursor = "skipped" if status == "skipped" else "completed"
        module.suspension_id = ""
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

    @staticmethod
    def _turn_frame_for_player_module(state: Any, parent_module: ModuleRef) -> FrameState | None:
        for frame in reversed(state.runtime_frame_stack):
            if (
                frame.frame_type == "turn"
                and frame.created_by_module_id == parent_module.module_id
                and frame.status != "completed"
            ):
                return frame
        return None

    @staticmethod
    def _child_frame_for_module(state: Any, parent_module: ModuleRef) -> FrameState | None:
        for frame in reversed(state.runtime_frame_stack):
            if frame.created_by_module_id == parent_module.module_id:
                return frame
        return None

    @staticmethod
    def _turn_context(frame: FrameState) -> dict[str, Any]:
        for module in frame.module_queue:
            if module.module_type == "TurnStartModule":
                return dict(module.payload)
        return {}

    @staticmethod
    def _skip_remaining_modules(frame: FrameState) -> None:
        for module in frame.module_queue:
            if module.status in {"queued", "running", "suspended"}:
                module.status = "skipped"
        frame.active_module_id = None

    def _complete_turn_frame_and_parent(self, state: Any, turn_frame: FrameState) -> None:
        turn_frame.status = "completed"
        turn_frame.active_module_id = None
        parent_module_id = turn_frame.created_by_module_id
        if not parent_module_id:
            return
        round_frame = self._active_round_frame(state)
        if round_frame is None:
            return
        for module in round_frame.module_queue:
            if module.module_id == parent_module_id and module.status in {"queued", "running", "suspended"}:
                self._complete_module(state, round_frame, module)
                return
