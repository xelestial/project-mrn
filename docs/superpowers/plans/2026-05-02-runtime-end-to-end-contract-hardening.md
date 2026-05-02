# Runtime End-to-End Contract Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every round/turn/sequence/simultaneous action legal in the engine only when it is also legal in backend persistence, Redis-backed runtime flow, WebSocket replay, and frontend projection.

**Architecture:** Establish a single runtime phase contract, enforce it at engine module insertion and backend stream/commit boundaries, then make frontend selectors consume only phase-consistent projections. Redis remains an atomic store and queue; semantic validation happens before Redis writes and before projected view_state is trusted.

**Tech Stack:** Python engine/runtime modules, Python FastAPI backend services, Redis persistence layer, TypeScript React frontend, Vitest, pytest.

---

## 0. Contract Scope

### 0-1. Runtime Frames

| Frame | Purpose | Allowed examples | Forbidden examples |
| --- | --- | --- | --- |
| `round` | Round-level setup, turn scheduling, player-turn slots, round cleanup | `RoundStartModule`, `WeatherModule`, `DraftModule`, `TurnSchedulerModule`, `PlayerTurnModule`, `RoundEndCardFlipModule`, `RoundCleanupAndNextRoundModule` | `DiceRollModule`, `MapMoveModule`, `TurnEndSnapshotModule` unless represented as completed child turn result |
| `turn` | One player's main turn body | `TurnStartModule`, `PendingMarkResolutionModule`, `CharacterStartModule`, `TrickWindowModule`, `DiceRollModule`, `MapMoveModule`, `ArrivalTileModule`, `FortuneResolveModule`, `TurnEndSnapshotModule` | `DraftModule`, `RoundEndCardFlipModule`, `ResupplyModule` |
| `sequence` | Nested follow-up work caused by a turn module | `TrickResolveModule`, `PurchaseDecisionModule`, `PurchaseCommitModule`, `LandingPostEffectsModule`, `FortuneResolveModule`, `LegacyActionAdapterModule` | `DraftModule`, `RoundEndCardFlipModule`, ordinary `ResupplyModule` |
| `simultaneous` | All-required or batch-style concurrent response/commit work | `ResupplyModule`, `SimultaneousPromptBatchModule`, `SimultaneousCommitModule`, `CompleteSimultaneousResolutionModule` | `DiceRollModule`, `MapMoveModule`, `TurnEndSnapshotModule`, `DraftModule` |

### 0-2. Round Action Matrix

Each round may contain these action groups. Every group must be controlled from engine to frontend.

| Round action group | Engine owner | Backend/Redis authority | Frontend visibility rule |
| --- | --- | --- | --- |
| Round start | `RoundStartModule` in `RoundFrame` | publish only if `frame_type=round`, `module_type=RoundStartModule`, no active turn prompt | `runtime.round_stage=round_setup`, no `turn_stage` mutation |
| Weather | `WeatherModule` in `RoundFrame` | one weather event per round idempotency key | show weather in round/setup context; may be copied into later turn context as persisted weather only |
| Draft pick/final choice | `DraftModule` in `RoundFrame` | prompt and events must carry round context, no turn frame/module | active draft UI only; must not append to previous `turn_stage.progress_codes` |
| Turn scheduling | `TurnSchedulerModule` in `RoundFrame` | order generated once per round and persisted in checkpoint | show order/progress outside current turn body |
| Player turn | `PlayerTurnModule` in `RoundFrame`, child `TurnFrame`/`SequenceFrame` work | stream events must match active turn round/turn/actor or active child frame | only same round+turn events can mutate `turn_stage` |
| Marker immediate effects | `PendingMarkResolutionModule`/`ImmediateMarkerTransferModule` at start of target player's turn | may occur before card flip; must carry current turn frame | displayed as early turn progress, not round-end marker flip |
| Trick sequence | `Trick*Module` in `SequenceFrame` created by active turn module | prompt continuation must include `resume_token`, `frame_id`, `module_id`, `module_type`, sequence id | hand/trick UI active only when runtime active sequence is trick |
| Dice/move/arrival | `DiceRollModule`, `MapMoveModule`, `ArrivalTileModule` | event must match active actor round+turn | displayed in current turn only |
| Fortune follow-up | `FortuneResolveModule` in turn/sequence | any inserted extra action must be queued through runtime module API | displayed in current turn/sequence only |
| Concurrent resupply | `SimultaneousResolutionFrame` | all participant prompts share `batch_id`; commit only when all required responses exist or policy timeout default applies | simultaneous response surface; must not supersede unrelated single-player prompts |
| Turn end | `TurnEndSnapshotModule` in active turn completion contract | turn completion cannot publish round-end card flip | closes current turn UI |
| Round-end card flip | `RoundEndCardFlipModule` in `RoundFrame` | allowed only after all `PlayerTurnModule`s completed/skipped | show as round-end stage, never as current turn progress |
| Cleanup/next round | `RoundCleanupAndNextRoundModule` | starts next round only after card flip/cleanup complete | clear stale prompt/turn stage before next draft |

## 1. File Structure

### 1-1. Engine

- Create `GPT/runtime_modules/catalog.py`
  - Single source of truth for module placement, event-code ownership, prompt request ownership, and sequence/simultaneous constraints.
- Modify `GPT/runtime_modules/queue.py`
  - Delegate module/frame checks to `catalog.py`.
- Modify `GPT/runtime_modules/sequence_modules.py`
  - Remove ordinary `ResupplyModule` from action sequence path.
  - Keep turn completion legal only through explicit contract, not accidental generic sequence allowance.
- Modify `GPT/runtime_modules/runner.py`
  - Route `resolve_supply_threshold` to `build_resupply_frame()` when simultaneous runtime flag is enabled.
  - Never allow round-end card flip while a child turn/sequence/simultaneous frame is active.
- Modify tests:
  - `GPT/test_runtime_module_contracts.py`
  - `GPT/test_runtime_sequence_modules.py`
  - `GPT/test_runtime_simultaneous_modules.py`

### 1-2. Backend

- Create `apps/server/src/domain/runtime_semantic_guard.py`
  - Validate event payloads, prompt payloads, checkpoint frame stacks, and view_state/runtime consistency before stream publish or runtime commit.
- Modify `apps/server/src/services/stream_service.py`
  - Run guard before projection and before Redis publish.
- Modify `apps/server/src/services/runtime_service.py`
  - Run checkpoint guard before `commit_transition()`.
- Modify `apps/server/src/services/prompt_service.py`
  - Validate `module_type` on decision submission.
  - Enforce batch prompt fields for simultaneous prompts.
- Modify `apps/server/src/domain/view_state/turn_selector.py`
  - Prevent round/draft/final prompts from mutating an existing turn stage.
- Modify `apps/server/src/domain/view_state/runtime_selector.py`
  - Normalize draft request types: `draft_card`, `final_character`, `final_character_choice`.
  - Mark `card_flip_legal` only when latest runtime module is `RoundEndCardFlipModule` and no active turn child remains.
- Add/modify tests:
  - `apps/server/tests/test_runtime_semantic_guard.py`
  - `apps/server/tests/test_view_state_turn_selector.py`
  - `apps/server/tests/test_view_state_runtime_projection.py`
  - `apps/server/tests/test_prompt_module_continuation.py`
  - `apps/server/tests/test_stream_service.py`

### 1-3. Frontend

- Modify `apps/web/src/core/contracts/stream.ts`
  - Add optional continuation fields to outbound decisions.
- Modify `apps/web/src/domain/selectors/promptSelectors.ts`
  - Preserve `resume_token`, `frame_id`, `module_id`, `module_type`, `batch_id` from prompt payload.
- Modify `apps/web/src/hooks/useGameStream.ts`
  - Send continuation fields with decisions.
- Modify `apps/web/src/domain/store/gameStreamReducer.ts`
  - Do not fast-forward to stale projected messages that conflict with latest known runtime path.
- Modify `apps/web/src/domain/selectors/streamSelectors.ts`
  - Ignore backend `turn_stage` when runtime projection says current stage is draft, turn scheduler, round-end card flip, or cleanup.
- Add/modify tests:
  - `apps/web/src/domain/selectors/promptSelectors.spec.ts`
  - `apps/web/src/domain/store/gameStreamReducer.spec.ts`
  - `apps/web/src/domain/selectors/streamSelectors.spec.ts`

### 1-4. Docs and Verification

- Create `docs/runtime/end-to-end-contract.md`
  - Human-readable engine/backend/frontend contract.
- Create `docs/runtime/round-action-control-matrix.md`
  - Round action matrix from this plan, kept close to implementation.

## 2. Task Plan

### Task 1: Engine Module Catalog and Placement Rules

**Files:**
- Create: `GPT/runtime_modules/catalog.py`
- Modify: `GPT/runtime_modules/queue.py`
- Test: `GPT/test_runtime_module_contracts.py`

- [ ] **Step 1: Write failing placement tests**

Add these tests to `GPT/test_runtime_module_contracts.py`:

```python
def test_round_end_card_flip_rejected_in_turn_frame() -> None:
    frame = FrameState(frame_id="turn:0:p0", frame_type="turn", owner_player_id=0, parent_frame_id=None)

    with pytest.raises(QueueValidationError, match="RoundEndCardFlipModule"):
        FrameQueueApi([frame]).apply([
            {"op": "push_back", "target_frame_id": frame.frame_id, "module": _module("RoundEndCardFlipModule")}
        ])


def test_resupply_module_rejected_in_action_sequence_frame() -> None:
    frame = FrameState(frame_id="seq:action:0:p0:0", frame_type="sequence", owner_player_id=0, parent_frame_id="turn:0:p0")
    frame.metadata = {"sequence_kind": "action"} if hasattr(frame, "metadata") else {}

    with pytest.raises(QueueValidationError, match="ResupplyModule"):
        FrameQueueApi([frame]).apply([
            {"op": "push_back", "target_frame_id": frame.frame_id, "module": _module("ResupplyModule")}
        ])
```

Run:

```bash
PYTHONPATH=GPT pytest GPT/test_runtime_module_contracts.py -q
```

Expected: the new `ResupplyModule` sequence test fails until catalog validation is added.

- [ ] **Step 2: Create catalog**

Create `GPT/runtime_modules/catalog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

FrameType = Literal["round", "turn", "sequence", "simultaneous"]


@dataclass(frozen=True)
class ModuleRule:
    module_type: str
    allowed_frame_types: frozenset[FrameType]
    round_stage: str = ""
    turn_stage: str = ""
    sequence_kind: str = ""
    simultaneous_kind: str = ""


MODULE_RULES: dict[str, ModuleRule] = {
    "RoundStartModule": ModuleRule("RoundStartModule", frozenset({"round"}), round_stage="round_setup"),
    "WeatherModule": ModuleRule("WeatherModule", frozenset({"round"}), round_stage="round_setup"),
    "DraftModule": ModuleRule("DraftModule", frozenset({"round"}), round_stage="draft"),
    "TurnSchedulerModule": ModuleRule("TurnSchedulerModule", frozenset({"round"}), round_stage="turn_scheduler"),
    "PlayerTurnModule": ModuleRule("PlayerTurnModule", frozenset({"round"}), round_stage="player_turn"),
    "RoundEndCardFlipModule": ModuleRule("RoundEndCardFlipModule", frozenset({"round"}), round_stage="round_end_card_flip"),
    "RoundCleanupAndNextRoundModule": ModuleRule("RoundCleanupAndNextRoundModule", frozenset({"round"}), round_stage="round_cleanup"),
    "TurnStartModule": ModuleRule("TurnStartModule", frozenset({"turn"}), turn_stage="turn_start"),
    "PendingMarkResolutionModule": ModuleRule("PendingMarkResolutionModule", frozenset({"turn", "sequence"}), turn_stage="mark_resolution"),
    "CharacterStartModule": ModuleRule("CharacterStartModule", frozenset({"turn"}), turn_stage="character_start"),
    "ImmediateMarkerTransferModule": ModuleRule("ImmediateMarkerTransferModule", frozenset({"turn"}), turn_stage="marker_transfer"),
    "TrickWindowModule": ModuleRule("TrickWindowModule", frozenset({"turn"}), turn_stage="trick_window"),
    "DiceRollModule": ModuleRule("DiceRollModule", frozenset({"turn"}), turn_stage="dice"),
    "MapMoveModule": ModuleRule("MapMoveModule", frozenset({"turn", "sequence"}), turn_stage="movement"),
    "ArrivalTileModule": ModuleRule("ArrivalTileModule", frozenset({"turn", "sequence"}), turn_stage="arrival"),
    "FortuneResolveModule": ModuleRule("FortuneResolveModule", frozenset({"turn", "sequence"}), turn_stage="fortune"),
    "TurnEndSnapshotModule": ModuleRule("TurnEndSnapshotModule", frozenset({"turn", "sequence"}), turn_stage="turn_end", sequence_kind="turn_completion"),
    "TrickChoiceModule": ModuleRule("TrickChoiceModule", frozenset({"sequence"}), sequence_kind="trick"),
    "TrickSkipModule": ModuleRule("TrickSkipModule", frozenset({"sequence"}), sequence_kind="trick"),
    "TrickResolveModule": ModuleRule("TrickResolveModule", frozenset({"sequence"}), sequence_kind="trick"),
    "TrickDiscardModule": ModuleRule("TrickDiscardModule", frozenset({"sequence"}), sequence_kind="trick"),
    "TrickDeferredFollowupsModule": ModuleRule("TrickDeferredFollowupsModule", frozenset({"sequence"}), sequence_kind="trick"),
    "TrickVisibilitySyncModule": ModuleRule("TrickVisibilitySyncModule", frozenset({"sequence"}), sequence_kind="trick"),
    "PurchaseDecisionModule": ModuleRule("PurchaseDecisionModule", frozenset({"sequence"}), sequence_kind="action"),
    "PurchaseCommitModule": ModuleRule("PurchaseCommitModule", frozenset({"sequence"}), sequence_kind="action"),
    "UnownedPostPurchaseModule": ModuleRule("UnownedPostPurchaseModule", frozenset({"sequence"}), sequence_kind="action"),
    "ScoreTokenPlacementPromptModule": ModuleRule("ScoreTokenPlacementPromptModule", frozenset({"sequence"}), sequence_kind="action"),
    "ScoreTokenPlacementCommitModule": ModuleRule("ScoreTokenPlacementCommitModule", frozenset({"sequence"}), sequence_kind="action"),
    "LandingPostEffectsModule": ModuleRule("LandingPostEffectsModule", frozenset({"sequence"}), sequence_kind="action"),
    "TrickTileRentModifierModule": ModuleRule("TrickTileRentModifierModule", frozenset({"sequence"}), sequence_kind="action"),
    "LegacyActionAdapterModule": ModuleRule("LegacyActionAdapterModule", frozenset({"sequence"}), sequence_kind="action"),
    "ResupplyModule": ModuleRule("ResupplyModule", frozenset({"simultaneous"}), simultaneous_kind="resupply"),
    "SimultaneousPromptBatchModule": ModuleRule("SimultaneousPromptBatchModule", frozenset({"simultaneous"})),
    "SimultaneousCommitModule": ModuleRule("SimultaneousCommitModule", frozenset({"simultaneous"})),
    "CompleteSimultaneousResolutionModule": ModuleRule("CompleteSimultaneousResolutionModule", frozenset({"simultaneous"})),
}


def module_rule(module_type: str) -> ModuleRule | None:
    return MODULE_RULES.get(module_type)


def validate_module_placement(module_type: str, frame_type: str, *, frame_id: str = "") -> None:
    rule = module_rule(module_type)
    if rule is None:
        return
    if frame_type not in rule.allowed_frame_types:
        location = f" in {frame_id}" if frame_id else ""
        allowed = ", ".join(sorted(rule.allowed_frame_types))
        raise ValueError(f"{module_type} is not allowed in {frame_type} frame{location}; allowed: {allowed}")
```

- [ ] **Step 3: Use catalog from queue validation**

Modify `GPT/runtime_modules/queue.py`:

```python
from .catalog import validate_module_placement
```

Replace `_validate_module_for_frame()` body with:

```python
    @staticmethod
    def _validate_module_for_frame(frame: FrameState, module: ModuleRef) -> None:
        try:
            validate_module_placement(module.module_type, frame.frame_type, frame_id=frame.frame_id)
        except ValueError as exc:
            raise QueueValidationError(str(exc)) from exc
```

- [ ] **Step 4: Run engine contract tests**

Run:

```bash
PYTHONPATH=GPT pytest GPT/test_runtime_module_contracts.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add GPT/runtime_modules/catalog.py GPT/runtime_modules/queue.py GPT/test_runtime_module_contracts.py
git commit -m "feat: centralize runtime module placement rules"
```

### Task 2: Route Resupply Through Simultaneous Resolution Only

**Files:**
- Modify: `GPT/runtime_modules/sequence_modules.py`
- Modify: `GPT/runtime_modules/runner.py`
- Test: `GPT/test_runtime_sequence_modules.py`
- Test: `GPT/test_runtime_simultaneous_modules.py`

- [ ] **Step 1: Write failing tests for resupply routing**

Add to `GPT/test_runtime_sequence_modules.py`:

```python
def test_supply_threshold_action_is_not_built_as_action_sequence_module() -> None:
    frame = build_action_sequence_frame(
        1,
        0,
        0,
        [{"type": "resolve_supply_threshold", "actor_player_id": 0}],
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        session_id="s1",
    )

    assert all(module.module_type != "ResupplyModule" for module in frame.module_queue)
    assert frame.module_queue[0].module_type == "LegacyActionAdapterModule"
```

Add to `GPT/test_runtime_simultaneous_modules.py`:

```python
def test_resupply_frame_contains_batch_commit_and_complete_modules() -> None:
    frame = build_resupply_frame(
        1,
        0,
        parent_frame_id="turn:1:p0",
        parent_module_id="mod:turn:1:p0:arrival",
        session_id="s1",
        participants=[0, 1, 2],
    )

    assert frame.frame_type == "simultaneous"
    assert [module.module_type for module in frame.module_queue] == [
        "ResupplyModule",
        "SimultaneousCommitModule",
        "CompleteSimultaneousResolutionModule",
    ]
    assert frame.module_queue[0].payload["participants"] == [0, 1, 2]
```

Run:

```bash
PYTHONPATH=GPT pytest GPT/test_runtime_sequence_modules.py GPT/test_runtime_simultaneous_modules.py -q
```

Expected: first test fails while `resolve_supply_threshold` still maps directly to `ResupplyModule`.

- [ ] **Step 2: Remove direct action mapping**

In `GPT/runtime_modules/sequence_modules.py`, remove `"ResupplyModule"` from `ACTION_SEQUENCE_MODULE_TYPES` and remove this mapping:

```python
"resolve_supply_threshold": "ResupplyModule",
```

The fallback `LegacyActionAdapterModule` remains until `runner.py` promotes that action into a simultaneous frame.

- [ ] **Step 3: Promote supply threshold action in runner**

In `GPT/runtime_modules/runner.py`, find the branch that promotes `pending_actions` to `build_action_sequence_frame()`. Before building the generic action frame, split supply-threshold actions:

```python
from .simultaneous import build_resupply_frame


def _split_supply_threshold_actions(actions: list[dict]) -> tuple[list[dict], list[dict]]:
    supply_actions: list[dict] = []
    other_actions: list[dict] = []
    for action in actions:
        if isinstance(action, dict) and str(action.get("type") or "") == "resolve_supply_threshold":
            supply_actions.append(action)
        else:
            other_actions.append(action)
    return supply_actions, other_actions
```

Use it in the pending-action promotion path:

```python
supply_actions, ordinary_actions = _split_supply_threshold_actions(pending_actions)
for index, action in enumerate(supply_actions):
    participants = action.get("participants")
    if not isinstance(participants, list):
        participants = list(range(int(getattr(state.config, "player_count", 0) or 0)))
    state.runtime_frame_stack.append(
        build_resupply_frame(
            int(getattr(state, "rounds_completed", 0) or 0) + 1,
            sequence_ordinal + index,
            parent_frame_id=parent_frame_id,
            parent_module_id=parent_module_id,
            session_id=session_id,
            participants=[int(player_id) for player_id in participants],
        )
    )
if ordinary_actions:
    state.runtime_frame_stack.append(
        build_action_sequence_frame(
            round_index,
            player_id,
            sequence_ordinal + len(supply_actions),
            ordinary_actions,
            parent_frame_id=parent_frame_id,
            parent_module_id=parent_module_id,
            session_id=session_id,
        )
    )
```

Keep exact variable names aligned with the existing promotion function when implementing.

- [ ] **Step 4: Run resupply tests**

Run:

```bash
PYTHONPATH=GPT pytest GPT/test_runtime_sequence_modules.py GPT/test_runtime_simultaneous_modules.py -q
```

Expected: PASS.

- [ ] **Step 5: Run full runtime module tests**

Run:

```bash
PYTHONPATH=GPT pytest GPT/test_runtime_module_contracts.py GPT/test_runtime_sequence_modules.py GPT/test_runtime_simultaneous_modules.py GPT/test_runtime_round_modules.py GPT/test_runtime_turn_modules.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add GPT/runtime_modules/sequence_modules.py GPT/runtime_modules/runner.py GPT/test_runtime_sequence_modules.py GPT/test_runtime_simultaneous_modules.py
git commit -m "feat: route resupply through simultaneous runtime frame"
```

### Task 3: Backend Runtime Semantic Guard

**Files:**
- Create: `apps/server/src/domain/runtime_semantic_guard.py`
- Modify: `apps/server/src/services/stream_service.py`
- Modify: `apps/server/src/services/runtime_service.py`
- Test: `apps/server/tests/test_runtime_semantic_guard.py`
- Test: `apps/server/tests/test_stream_service.py`

- [ ] **Step 1: Write semantic guard tests**

Create `apps/server/tests/test_runtime_semantic_guard.py`:

```python
from __future__ import annotations

import pytest

from apps.server.src.domain.runtime_semantic_guard import (
    RuntimeSemanticViolation,
    validate_checkpoint_payload,
    validate_stream_payload,
)


def test_rejects_draft_module_in_turn_frame_stream_payload() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="DraftModule"):
        validate_stream_payload(
            history=[],
            msg_type="event",
            payload={
                "event_type": "draft_pick",
                "round_index": 2,
                "turn_index": 4,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:2:p0",
                    "module_type": "DraftModule",
                    "module_id": "mod:draft",
                },
            },
        )


def test_rejects_marker_flip_in_active_turn_context() -> None:
    history = [
        {
            "type": "event",
            "seq": 10,
            "payload": {
                "event_type": "turn_start",
                "round_index": 1,
                "turn_index": 3,
                "acting_player_id": 0,
            },
        }
    ]

    with pytest.raises(RuntimeSemanticViolation, match="RoundEndCardFlipModule"):
        validate_stream_payload(
            history=history,
            msg_type="event",
            payload={
                "event_type": "marker_flip",
                "round_index": 1,
                "turn_index": 3,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:1:p0",
                    "module_type": "RoundEndCardFlipModule",
                    "module_id": "mod:flip",
                },
            },
        )


def test_checkpoint_rejects_round_card_flip_with_suspended_player_turn() -> None:
    with pytest.raises(RuntimeSemanticViolation, match="card flip"):
        validate_checkpoint_payload(
            {
                "runtime_runner_kind": "module",
                "runtime_frame_stack": [
                    {
                        "frame_id": "round:1",
                        "frame_type": "round",
                        "status": "running",
                        "active_module_id": "mod:flip",
                        "module_queue": [
                            {"module_id": "mod:p0", "module_type": "PlayerTurnModule", "status": "suspended"},
                            {"module_id": "mod:flip", "module_type": "RoundEndCardFlipModule", "status": "running"},
                        ],
                    }
                ],
            }
        )
```

Run:

```bash
pytest apps/server/tests/test_runtime_semantic_guard.py -q
```

Expected: FAIL because the guard file does not exist.

- [ ] **Step 2: Implement guard**

Create `apps/server/src/domain/runtime_semantic_guard.py`:

```python
from __future__ import annotations

from typing import Any


class RuntimeSemanticViolation(ValueError):
    pass


MODULE_ALLOWED_FRAMES: dict[str, set[str]] = {
    "RoundStartModule": {"round"},
    "WeatherModule": {"round"},
    "DraftModule": {"round"},
    "TurnSchedulerModule": {"round"},
    "PlayerTurnModule": {"round"},
    "RoundEndCardFlipModule": {"round"},
    "RoundCleanupAndNextRoundModule": {"round"},
    "TurnStartModule": {"turn"},
    "PendingMarkResolutionModule": {"turn", "sequence"},
    "CharacterStartModule": {"turn"},
    "ImmediateMarkerTransferModule": {"turn"},
    "TrickWindowModule": {"turn"},
    "DiceRollModule": {"turn"},
    "MapMoveModule": {"turn", "sequence"},
    "ArrivalTileModule": {"turn", "sequence"},
    "FortuneResolveModule": {"turn", "sequence"},
    "TurnEndSnapshotModule": {"turn", "sequence"},
    "TrickChoiceModule": {"sequence"},
    "TrickSkipModule": {"sequence"},
    "TrickResolveModule": {"sequence"},
    "TrickDiscardModule": {"sequence"},
    "TrickDeferredFollowupsModule": {"sequence"},
    "TrickVisibilitySyncModule": {"sequence"},
    "PurchaseDecisionModule": {"sequence"},
    "PurchaseCommitModule": {"sequence"},
    "UnownedPostPurchaseModule": {"sequence"},
    "ScoreTokenPlacementPromptModule": {"sequence"},
    "ScoreTokenPlacementCommitModule": {"sequence"},
    "LandingPostEffectsModule": {"sequence"},
    "TrickTileRentModifierModule": {"sequence"},
    "LegacyActionAdapterModule": {"sequence"},
    "ResupplyModule": {"simultaneous"},
    "SimultaneousPromptBatchModule": {"simultaneous"},
    "SimultaneousCommitModule": {"simultaneous"},
    "CompleteSimultaneousResolutionModule": {"simultaneous"},
}

ROUND_ONLY_EVENTS = {
    "round_start",
    "weather_reveal",
    "draft_pick",
    "final_character_choice",
    "round_order",
    "marker_flip",
    "active_flip",
}

TURN_EVENTS = {
    "turn_start",
    "mark_resolved",
    "mark_queued",
    "trick_window_open",
    "dice_roll",
    "player_move",
    "landing_resolved",
    "tile_purchased",
    "rent_paid",
    "fortune_drawn",
    "fortune_resolved",
    "lap_reward_chosen",
    "turn_end_snapshot",
}

EVENT_REQUIRED_MODULES = {
    "draft_pick": {"DraftModule"},
    "final_character_choice": {"DraftModule"},
    "marker_flip": {"RoundEndCardFlipModule"},
    "active_flip": {"RoundEndCardFlipModule"},
}


def validate_stream_payload(*, history: list[dict], msg_type: str, payload: dict[str, Any]) -> None:
    runtime_module = _record(payload.get("runtime_module"))
    if runtime_module:
        _validate_runtime_module(runtime_module)
    event_type = str(payload.get("event_type") or "").strip()
    if msg_type == "prompt":
        _validate_prompt_payload(payload)
    if msg_type == "event" and event_type:
        _validate_event_payload(event_type, payload, runtime_module)
        _validate_event_against_active_turn(history, event_type, payload, runtime_module)
    checkpoint = _record(payload.get("engine_checkpoint"))
    if checkpoint:
        validate_checkpoint_payload(checkpoint)


def validate_checkpoint_payload(payload: dict[str, Any]) -> None:
    frames = payload.get("runtime_frame_stack")
    runtime_state = _record(payload.get("runtime_state")) or {}
    if not isinstance(frames, list):
        frames = runtime_state.get("frame_stack")
    if not isinstance(frames, list):
        return
    for frame in frames:
        if not isinstance(frame, dict):
            continue
        frame_type = str(frame.get("frame_type") or "").strip()
        for module in frame.get("module_queue") or []:
            if isinstance(module, dict):
                _validate_runtime_module({**module, "frame_type": frame_type, "frame_id": frame.get("frame_id")})
        _validate_card_flip_not_before_turns_complete(frame)


def _validate_runtime_module(module: dict[str, Any]) -> None:
    module_type = str(module.get("module_type") or "").strip()
    frame_type = str(module.get("frame_type") or "").strip()
    if not module_type or not frame_type:
        return
    allowed = MODULE_ALLOWED_FRAMES.get(module_type)
    if allowed and frame_type not in allowed:
        raise RuntimeSemanticViolation(f"{module_type} is not allowed in {frame_type} frame")


def _validate_event_payload(event_type: str, payload: dict[str, Any], runtime_module: dict[str, Any] | None) -> None:
    expected_modules = EVENT_REQUIRED_MODULES.get(event_type)
    if expected_modules and runtime_module:
        module_type = str(runtime_module.get("module_type") or "")
        if module_type not in expected_modules:
            raise RuntimeSemanticViolation(f"{event_type} requires one of {sorted(expected_modules)}, got {module_type}")
    if event_type in ROUND_ONLY_EVENTS and runtime_module:
        frame_type = str(runtime_module.get("frame_type") or "")
        if frame_type and frame_type != "round":
            raise RuntimeSemanticViolation(f"{event_type} is round-only and cannot be emitted from {frame_type}")


def _validate_event_against_active_turn(
    history: list[dict],
    event_type: str,
    payload: dict[str, Any],
    runtime_module: dict[str, Any] | None,
) -> None:
    if event_type not in ROUND_ONLY_EVENTS:
        return
    if event_type not in {"marker_flip", "active_flip", "draft_pick", "final_character_choice"}:
        return
    latest_turn = _latest_turn_start(history)
    if latest_turn is None:
        return
    if event_type in {"draft_pick", "final_character_choice"}:
        return
    if runtime_module and str(runtime_module.get("module_type") or "") == "RoundEndCardFlipModule":
        return
    raise RuntimeSemanticViolation(f"{event_type} cannot be projected as active turn progress")


def _validate_prompt_payload(payload: dict[str, Any]) -> None:
    if str(payload.get("runner_kind") or payload.get("runtime_runner_kind") or "") != "module" and not payload.get("resume_token"):
        return
    for field in ("resume_token", "frame_id", "module_id", "module_type"):
        if not str(payload.get(field) or "").strip():
            raise RuntimeSemanticViolation(f"module prompt missing {field}")
    module_type = str(payload.get("module_type") or "")
    frame_id = str(payload.get("frame_id") or "")
    frame_type = _frame_type_from_frame_id(frame_id)
    if frame_type:
        _validate_runtime_module({"module_type": module_type, "frame_type": frame_type, "frame_id": frame_id})
    if module_type in {"ResupplyModule", "SimultaneousPromptBatchModule"} and not str(payload.get("batch_id") or "").strip():
        raise RuntimeSemanticViolation("simultaneous prompt missing batch_id")


def _validate_card_flip_not_before_turns_complete(frame: dict[str, Any]) -> None:
    if str(frame.get("frame_type") or "") != "round":
        return
    modules = [module for module in frame.get("module_queue") or [] if isinstance(module, dict)]
    active_module_id = str(frame.get("active_module_id") or "")
    active = next((module for module in modules if str(module.get("module_id") or "") == active_module_id), None)
    if not active or str(active.get("module_type") or "") != "RoundEndCardFlipModule":
        return
    pending_turns = [
        module
        for module in modules
        if str(module.get("module_type") or "") == "PlayerTurnModule"
        and str(module.get("status") or "queued") not in {"completed", "skipped"}
    ]
    if pending_turns:
        raise RuntimeSemanticViolation("card flip cannot run before all player turns complete")


def _latest_turn_start(history: list[dict]) -> dict[str, Any] | None:
    for message in reversed(history):
        payload = _record(message.get("payload")) or {}
        if str(payload.get("event_type") or "") == "turn_start":
            return payload
    return None


def _frame_type_from_frame_id(frame_id: str) -> str:
    if frame_id.startswith("round:"):
        return "round"
    if frame_id.startswith("turn:"):
        return "turn"
    if frame_id.startswith("seq:"):
        return "sequence"
    if frame_id.startswith("simul:"):
        return "simultaneous"
    return ""


def _record(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None
```

- [ ] **Step 3: Call guard from stream publish**

In `apps/server/src/services/stream_service.py`, import:

```python
from apps.server.src.domain.runtime_semantic_guard import validate_stream_payload
```

Inside `publish()`, after `history = ...` and before duplicate checks:

```python
validate_stream_payload(history=history, msg_type=msg_type, payload=enriched_payload)
```

- [ ] **Step 4: Call guard before runtime commit**

In `apps/server/src/services/runtime_service.py`, import:

```python
from apps.server.src.domain.runtime_semantic_guard import validate_checkpoint_payload
```

Before `self._game_state_store.commit_transition(...)`, after `payload = state.to_checkpoint_payload()`:

```python
validate_checkpoint_payload(payload)
```

- [ ] **Step 5: Add stream-service rejection test**

Add to `apps/server/tests/test_stream_service.py`:

```python
import pytest


def test_publish_rejects_runtime_impossible_module_placement() -> None:
    service = StreamService()

    async def _run() -> None:
        with pytest.raises(Exception, match="DraftModule"):
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "draft_pick",
                    "runtime_module": {
                        "frame_type": "turn",
                        "frame_id": "turn:1:p0",
                        "module_type": "DraftModule",
                        "module_id": "mod:draft",
                    },
                },
            )

    asyncio.run(_run())
```

- [ ] **Step 6: Run backend guard tests**

Run:

```bash
pytest apps/server/tests/test_runtime_semantic_guard.py apps/server/tests/test_stream_service.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/server/src/domain/runtime_semantic_guard.py apps/server/src/services/stream_service.py apps/server/src/services/runtime_service.py apps/server/tests/test_runtime_semantic_guard.py apps/server/tests/test_stream_service.py
git commit -m "feat: enforce runtime semantic guard before persistence"
```

### Task 4: Prompt Continuation and Simultaneous Batch Contract

**Files:**
- Modify: `apps/server/src/services/prompt_service.py`
- Test: `apps/server/tests/test_prompt_module_continuation.py`

- [ ] **Step 1: Write failing tests**

Add to `apps/server/tests/test_prompt_module_continuation.py`:

```python
def test_module_type_mismatch_rejected() -> None:
    service = PromptService()
    service.create_prompt("s1", _module_prompt())

    result = service.submit_decision(
        {
            "request_id": "req_1",
            "player_id": 1,
            "choice_id": "roll",
            "resume_token": "token_1",
            "frame_id": "turn:1:p0",
            "module_id": "mod:turn:1:p0:movement",
            "module_type": "DiceRollModule",
        }
    )

    assert result == {"status": "rejected", "reason": "module_mismatch"}


def test_simultaneous_module_prompt_requires_batch_id() -> None:
    service = PromptService()
    prompt = {
        **_module_prompt(),
        "request_id": "resupply_1:p1",
        "request_type": "resupply_choice",
        "frame_id": "simul:resupply:1:0",
        "module_id": "mod:simul:resupply:1:0:resupply",
        "module_type": "ResupplyModule",
    }

    with pytest.raises(ValueError, match="missing_batch_id"):
        service.create_prompt("s1", prompt)
```

Run:

```bash
pytest apps/server/tests/test_prompt_module_continuation.py -q
```

Expected: first new test fails because `module_type` is not compared; second fails until batch validation is added.

- [ ] **Step 2: Compare module_type during decision submit**

Modify `_module_decision_mismatch()` in `apps/server/src/services/prompt_service.py`:

```python
    for field, reason in (
        ("resume_token", "token_mismatch"),
        ("frame_id", "module_mismatch"),
        ("module_id", "module_mismatch"),
        ("module_type", "module_mismatch"),
    ):
```

- [ ] **Step 3: Require batch_id for simultaneous prompts**

Modify `_require_module_continuation()`:

```python
    module_type = str(prompt.get("module_type") or "").strip()
    frame_id = str(prompt.get("frame_id") or "").strip()
    if module_type in {"ResupplyModule", "SimultaneousPromptBatchModule"} or frame_id.startswith("simul:"):
        if not str(prompt.get("batch_id") or "").strip():
            raise ValueError("missing_batch_id")
```

- [ ] **Step 4: Run prompt tests**

Run:

```bash
pytest apps/server/tests/test_prompt_module_continuation.py apps/server/tests/test_prompt_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/services/prompt_service.py apps/server/tests/test_prompt_module_continuation.py
git commit -m "fix: validate module continuation decisions"
```

### Task 5: Backend Projection Separation for Round vs Turn

**Files:**
- Modify: `apps/server/src/domain/view_state/turn_selector.py`
- Modify: `apps/server/src/domain/view_state/runtime_selector.py`
- Test: `apps/server/tests/test_view_state_turn_selector.py`
- Test: `apps/server/tests/test_view_state_runtime_projection.py`

- [ ] **Step 1: Write failing turn selector regression**

Add to `apps/server/tests/test_view_state_turn_selector.py`:

```python
    def test_draft_prompt_after_turn_does_not_mutate_previous_turn_stage(self) -> None:
        view_state = build_turn_stage_view_state(
            [
                {
                    "type": "event",
                    "seq": 10,
                    "session_id": "s1",
                    "server_time_ms": 1,
                    "payload": {
                        "event_type": "turn_start",
                        "round_index": 1,
                        "turn_index": 4,
                        "acting_player_id": 2,
                        "character": "객주",
                    },
                },
                {
                    "type": "event",
                    "seq": 11,
                    "session_id": "s1",
                    "server_time_ms": 2,
                    "payload": {
                        "event_type": "turn_end_snapshot",
                        "round_index": 1,
                        "turn_index": 4,
                        "acting_player_id": 2,
                    },
                },
                {
                    "type": "prompt",
                    "seq": 12,
                    "session_id": "s1",
                    "server_time_ms": 3,
                    "payload": {
                        "request_id": "r2:draft:p0",
                        "request_type": "draft_card",
                        "player_id": 0,
                        "round_index": 2,
                        "public_context": {"round_index": 2, "draft_phase": 1},
                    },
                },
            ]
        )

        assert view_state["round_index"] == 1
        assert view_state["turn_index"] == 4
        assert view_state["prompt_request_type"] == "-"
        assert view_state["current_beat_event_code"] == "turn_end_snapshot"
        assert "prompt_active" not in view_state["progress_codes"]
```

Run:

```bash
pytest apps/server/tests/test_view_state_turn_selector.py -q
```

Expected: FAIL because current prompt branch accepts pre-character-selection prompts after turn start.

- [ ] **Step 2: Restrict prompt branch to same turn context**

In `apps/server/src/domain/view_state/turn_selector.py`, replace the prompt acceptance condition at the prompt branch with:

```python
            prompt_round, prompt_turn = _prompt_round_turn(payload)
            is_turn_scoped_prompt = (
                prompt_turn is not None
                and prompt_round == model["round_index"]
                and prompt_turn == model["turn_index"]
            )
            if request_type and (
                model["actor_player_id"] is None
                or model["actor_player_id"] == prompt_actor
            ) and is_turn_scoped_prompt:
```

Add helper near other helpers:

```python
def _prompt_round_turn(payload: dict) -> tuple[int | None, int | None]:
    public_context = _record(payload.get("public_context")) or {}
    round_index = _number(payload.get("round_index", public_context.get("round_index")))
    turn_index = _number(payload.get("turn_index", public_context.get("turn_index")))
    return round_index, turn_index
```

Do not use `_is_pre_character_selection_request_type()` in turn-stage prompt inclusion. Keep it only if another selector still needs it.

- [ ] **Step 3: Normalize runtime draft prompt detection**

In `apps/server/src/domain/view_state/runtime_selector.py`, modify `_is_draft_prompt()` to treat these request types as draft:

```python
return request_type in {"draft_card", "character_pick", "final_character", "final_character_choice"}
```

Add a runtime projection test in `apps/server/tests/test_view_state_runtime_projection.py`:

```python
def test_runtime_projection_treats_draft_card_prompt_as_draft_active() -> None:
    view_state = build_runtime_view_state(
        [
            {
                "type": "prompt",
                "seq": 1,
                "payload": {
                    "request_id": "r1:draft:p0",
                    "request_type": "draft_card",
                    "player_id": 0,
                    "runner_kind": "module",
                    "resume_token": "tok",
                    "frame_id": "round:1",
                    "module_id": "mod:round:1:draft",
                    "module_type": "DraftModule",
                },
            }
        ]
    )

    assert view_state["draft_active"] is True
    assert view_state["round_stage"] == "draft"
    assert view_state["turn_stage"] == ""
```

- [ ] **Step 4: Run projection tests**

Run:

```bash
pytest apps/server/tests/test_view_state_turn_selector.py apps/server/tests/test_view_state_runtime_projection.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/server/src/domain/view_state/turn_selector.py apps/server/src/domain/view_state/runtime_selector.py apps/server/tests/test_view_state_turn_selector.py apps/server/tests/test_view_state_runtime_projection.py
git commit -m "fix: separate round prompts from turn projection"
```

### Task 6: Frontend Decision Continuation and Projection Guard

**Files:**
- Modify: `apps/web/src/core/contracts/stream.ts`
- Modify: `apps/web/src/domain/selectors/promptSelectors.ts`
- Modify: `apps/web/src/hooks/useGameStream.ts`
- Modify: `apps/web/src/domain/selectors/streamSelectors.ts`
- Test: `apps/web/src/domain/selectors/promptSelectors.spec.ts`
- Test: `apps/web/src/domain/selectors/streamSelectors.spec.ts`

- [ ] **Step 1: Add failing prompt continuation selector test**

Add to `apps/web/src/domain/selectors/promptSelectors.spec.ts`:

```ts
it("preserves module continuation fields on the active prompt", () => {
  const prompt = selectActivePrompt([
    {
      type: "prompt",
      seq: 1,
      session_id: "s1",
      payload: {
        request_id: "req_move",
        request_type: "movement",
        player_id: 1,
        timeout_ms: 30000,
        resume_token: "tok_1",
        frame_id: "turn:1:p1",
        module_id: "mod:move",
        module_type: "MapMoveModule",
        legal_choices: [{ choice_id: "roll", title: "roll" }],
      },
    },
  ]);

  expect(prompt?.continuation).toEqual({
    resumeToken: "tok_1",
    frameId: "turn:1:p1",
    moduleId: "mod:move",
    moduleType: "MapMoveModule",
    batchId: null,
  });
});
```

- [ ] **Step 2: Add failing stream selector test for backend turn-stage override**

Add to `apps/web/src/domain/selectors/streamSelectors.spec.ts`:

```ts
it("does not apply backend turn_stage when runtime is in draft stage", () => {
  const model = selectCurrentTurnModel([
    {
      type: "event",
      seq: 1,
      session_id: "s1",
      payload: {
        event_type: "turn_start",
        round_index: 1,
        turn_index: 4,
        acting_player_id: 1,
      },
    },
    {
      type: "prompt",
      seq: 2,
      session_id: "s1",
      payload: {
        request_id: "r2:draft:p0",
        request_type: "draft_card",
        player_id: 0,
        view_state: {
          runtime: { round_stage: "draft", turn_stage: "", draft_active: true },
          turn_stage: {
            turn_start_seq: 1,
            actor_player_id: 1,
            round_index: 2,
            turn_index: 4,
            character: "-",
            current_beat_kind: "decision",
            current_beat_event_code: "prompt_active",
            current_beat_request_type: "draft_card",
            current_beat_seq: 2,
            focus_tile_index: null,
            focus_tile_indices: [],
            prompt_request_type: "draft_card",
            progress_codes: ["turn_start", "prompt_active"],
          },
        },
      },
    },
  ]);

  expect(model.round).toBe(1);
  expect(model.turn).toBe(4);
  expect(model.promptRequestType).toBe("-");
  expect(model.progressTrail).not.toContain("드래프트");
});
```

Run:

```bash
cd apps/web
npm test -- src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts
```

Expected: FAIL until fields and projection guard are implemented.

- [ ] **Step 3: Add continuation fields to contracts and prompt view model**

Modify `apps/web/src/domain/selectors/promptSelectors.ts`:

```ts
export type PromptContinuationViewModel = {
  resumeToken: string | null;
  frameId: string | null;
  moduleId: string | null;
  moduleType: string | null;
  batchId: string | null;
};
```

Add to `PromptViewModel`:

```ts
  continuation: PromptContinuationViewModel;
```

When building a prompt model from payload:

```ts
continuation: {
  resumeToken: stringOrEmpty(payload["resume_token"]) || null,
  frameId: stringOrEmpty(payload["frame_id"]) || null,
  moduleId: stringOrEmpty(payload["module_id"]) || null,
  moduleType: stringOrEmpty(payload["module_type"]) || null,
  batchId: stringOrEmpty(payload["batch_id"]) || null,
},
```

Modify `apps/web/src/core/contracts/stream.ts` outbound decision:

```ts
      resume_token?: string;
      frame_id?: string;
      module_id?: string;
      module_type?: string;
      batch_id?: string;
```

- [ ] **Step 4: Send continuation fields with decisions**

Modify `sendDecision()` in `apps/web/src/hooks/useGameStream.ts` to accept optional continuation:

```ts
  const sendDecision = (args: {
    requestId: string;
    playerId: number;
    choiceId: string;
    choicePayload?: Record<string, unknown>;
    continuation?: {
      resumeToken?: string | null;
      frameId?: string | null;
      moduleId?: string | null;
      moduleType?: string | null;
      batchId?: string | null;
    };
  }): boolean => {
```

Include fields in the outbound message:

```ts
      resume_token: args.continuation?.resumeToken ?? undefined,
      frame_id: args.continuation?.frameId ?? undefined,
      module_id: args.continuation?.moduleId ?? undefined,
      module_type: args.continuation?.moduleType ?? undefined,
      batch_id: args.continuation?.batchId ?? undefined,
```

Update UI decision call sites to pass `activePrompt.continuation`.

- [ ] **Step 5: Ignore backend turn_stage outside turn runtime stages**

In `apps/web/src/domain/selectors/streamSelectors.ts`, before applying `backendTurnStage`, read latest runtime projection and guard:

```ts
const runtime = selectRuntimeProjection(messages);
const roundOnlyRuntimeStage = runtime && ["round_setup", "draft", "turn_scheduler", "round_end_card_flip", "round_cleanup"].includes(runtime.roundStage);
if (backendTurnStage && !roundOnlyRuntimeStage) {
  // existing backendTurnStage override block
}
```

Keep manual fallback model building for old streams, but do not let backend `turn_stage` override the current model when runtime says this is round/draft/card-flip context.

- [ ] **Step 6: Run frontend selector tests**

Run:

```bash
cd apps/web
npm test -- src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add apps/web/src/core/contracts/stream.ts apps/web/src/domain/selectors/promptSelectors.ts apps/web/src/hooks/useGameStream.ts apps/web/src/domain/selectors/promptSelectors.spec.ts apps/web/src/domain/selectors/streamSelectors.ts apps/web/src/domain/selectors/streamSelectors.spec.ts
git commit -m "fix: carry runtime continuation and guard turn projection"
```

### Task 7: Frontend Replay/Fast-Forward Guard

**Files:**
- Modify: `apps/web/src/domain/store/gameStreamReducer.ts`
- Test: `apps/web/src/domain/store/gameStreamReducer.spec.ts`

- [ ] **Step 1: Add failing stale projection fast-forward test**

Add to `apps/web/src/domain/store/gameStreamReducer.spec.ts`:

```ts
it("does not fast-forward to a projected message from an older runtime frame", () => {
  const state = gameStreamReducer(initialGameStreamState, {
    type: "message",
    message: {
      type: "event",
      seq: 10,
      session_id: "s1",
      payload: {
        event_type: "turn_start",
        runtime_module: {
          frame_id: "turn:2:p1",
          module_id: "mod:turn:2:p1:start",
          module_type: "TurnStartModule",
        },
      },
    },
  });

  const next = gameStreamReducer(state, {
    type: "message",
    message: {
      type: "prompt",
      seq: 12,
      session_id: "s1",
      payload: {
        request_id: "old:draft",
        request_type: "draft_card",
        view_state: {
          runtime: {
            latest_module_path: ["round:1", "mod:round:1:draft"],
            round_stage: "draft",
            draft_active: true,
          },
        },
      },
    },
  });

  expect(next.lastSeq).toBe(10);
  expect(next.pendingBySeq[12]).toBeDefined();
});
```

Run:

```bash
cd apps/web
npm test -- src/domain/store/gameStreamReducer.spec.ts
```

Expected: FAIL until stale projection guard is added.

- [ ] **Step 2: Add projection compatibility helper**

In `apps/web/src/domain/store/gameStreamReducer.ts`, add:

```ts
function runtimeFramePath(message: InboundMessage): string[] {
  const payload = typeof message.payload === "object" && message.payload !== null ? message.payload as Record<string, unknown> : {};
  const viewState = typeof payload["view_state"] === "object" && payload["view_state"] !== null ? payload["view_state"] as Record<string, unknown> : null;
  const runtime = viewState && typeof viewState["runtime"] === "object" && viewState["runtime"] !== null ? viewState["runtime"] as Record<string, unknown> : null;
  const path = runtime?.["latest_module_path"];
  return Array.isArray(path) ? path.filter((item): item is string => typeof item === "string") : [];
}

function projectedMessageIsCompatibleWithLatest(messages: InboundMessage[], candidate: InboundMessage): boolean {
  const candidatePath = runtimeFramePath(candidate);
  if (candidatePath.length === 0) {
    return true;
  }
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const latestPath = runtimeFramePath(messages[index]);
    if (latestPath.length === 0) {
      continue;
    }
    return latestPath[0] === candidatePath[0];
  }
  return true;
}
```

In `flushPendingMessages()`, change `firstProjectedSeq` predicate:

```ts
return Boolean(candidate && (carriesCurrentProjection(candidate) || candidate.type === "prompt") && projectedMessageIsCompatibleWithLatest(nextMessages, candidate));
```

- [ ] **Step 3: Run reducer tests**

Run:

```bash
cd apps/web
npm test -- src/domain/store/gameStreamReducer.spec.ts
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/web/src/domain/store/gameStreamReducer.ts apps/web/src/domain/store/gameStreamReducer.spec.ts
git commit -m "fix: reject stale projected replay fast-forward"
```

### Task 8: End-to-End Contract Verification Suite

**Files:**
- Create: `apps/server/tests/test_runtime_end_to_end_contract.py`
- Modify as needed: `apps/server/tests/test_runtime_service.py`
- Optional frontend: `apps/web/src/domain/selectors/streamSelectors.spec.ts`

- [ ] **Step 1: Add log-shape regression test**

Create `apps/server/tests/test_runtime_end_to_end_contract.py`:

```python
from __future__ import annotations

from apps.server.src.domain.view_state.projector import project_view_state


def test_next_round_draft_does_not_pollute_previous_turn_stage() -> None:
    messages = [
        {
            "type": "event",
            "seq": 1,
            "session_id": "s1",
            "payload": {
                "event_type": "turn_start",
                "round_index": 1,
                "turn_index": 4,
                "acting_player_id": 2,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:1:p2",
                    "module_type": "TurnStartModule",
                    "module_id": "mod:turn:start",
                },
            },
        },
        {
            "type": "event",
            "seq": 2,
            "session_id": "s1",
            "payload": {
                "event_type": "turn_end_snapshot",
                "round_index": 1,
                "turn_index": 4,
                "acting_player_id": 2,
                "runtime_module": {
                    "frame_type": "sequence",
                    "frame_id": "seq:turn_completion:1:p2:0",
                    "module_type": "TurnEndSnapshotModule",
                    "module_id": "mod:turn:end",
                },
            },
        },
        {
            "type": "prompt",
            "seq": 3,
            "session_id": "s1",
            "payload": {
                "request_id": "r2:draft:p0",
                "request_type": "draft_card",
                "player_id": 0,
                "runner_kind": "module",
                "resume_token": "tok",
                "frame_id": "round:2",
                "module_id": "mod:round:2:draft",
                "module_type": "DraftModule",
                "public_context": {"round_index": 2, "draft_phase": 1},
            },
        },
    ]

    view_state = project_view_state(messages)
    assert view_state["runtime"]["round_stage"] == "draft"
    assert view_state["runtime"]["draft_active"] is True
    assert view_state["turn_stage"]["round_index"] == 1
    assert view_state["turn_stage"]["current_beat_event_code"] == "turn_end_snapshot"
    assert "prompt_active" not in view_state["turn_stage"]["progress_codes"]
```

Run:

```bash
pytest apps/server/tests/test_runtime_end_to_end_contract.py -q
```

Expected: PASS after Tasks 3-5.

- [ ] **Step 2: Add impossible event rejection test through StreamService**

Add to the same file:

```python
import asyncio
import pytest

from apps.server.src.services.stream_service import StreamService


def test_stream_service_rejects_round_end_flip_from_turn_frame() -> None:
    service = StreamService()

    async def _run() -> None:
        await service.publish(
            "s1",
            "event",
            {
                "event_type": "turn_start",
                "round_index": 1,
                "turn_index": 1,
                "acting_player_id": 0,
                "runtime_module": {
                    "frame_type": "turn",
                    "frame_id": "turn:1:p0",
                    "module_type": "TurnStartModule",
                    "module_id": "mod:turn:start",
                },
            },
        )
        with pytest.raises(Exception, match="RoundEndCardFlipModule"):
            await service.publish(
                "s1",
                "event",
                {
                    "event_type": "marker_flip",
                    "round_index": 1,
                    "turn_index": 1,
                    "runtime_module": {
                        "frame_type": "turn",
                        "frame_id": "turn:1:p0",
                        "module_type": "RoundEndCardFlipModule",
                        "module_id": "mod:flip",
                    },
                },
            )

    asyncio.run(_run())
```

- [ ] **Step 3: Run full targeted verification**

Run:

```bash
PYTHONPATH=GPT pytest \
  GPT/test_runtime_module_contracts.py \
  GPT/test_runtime_sequence_modules.py \
  GPT/test_runtime_simultaneous_modules.py \
  GPT/test_runtime_round_modules.py \
  GPT/test_runtime_turn_modules.py \
  apps/server/tests/test_runtime_semantic_guard.py \
  apps/server/tests/test_runtime_end_to_end_contract.py \
  apps/server/tests/test_prompt_module_continuation.py \
  apps/server/tests/test_view_state_turn_selector.py \
  apps/server/tests/test_view_state_runtime_projection.py \
  apps/server/tests/test_stream_service.py \
  -q
```

Expected: PASS.

- [ ] **Step 4: Run frontend targeted verification**

Run:

```bash
cd apps/web
npm test -- \
  src/domain/selectors/promptSelectors.spec.ts \
  src/domain/selectors/streamSelectors.spec.ts \
  src/domain/store/gameStreamReducer.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/server/tests/test_runtime_end_to_end_contract.py
git commit -m "test: lock runtime end-to-end phase contract"
```

### Task 9: Documentation and Control Matrix

**Files:**
- Create: `docs/runtime/end-to-end-contract.md`
- Create: `docs/runtime/round-action-control-matrix.md`

- [ ] **Step 1: Write end-to-end contract document**

Create `docs/runtime/end-to-end-contract.md`:

```markdown
# Runtime End-to-End Contract

## Authority

The engine is the source of legal game progression. Backend services, Redis persistence, WebSocket replay, and frontend selectors must reject or ignore states that contradict the engine runtime contract.

## Runtime Boundaries

- `RoundFrame`: setup, draft, turn scheduling, player-turn slots, round-end card flip, cleanup.
- `TurnFrame`: exactly one player's turn body.
- `SequenceFrame`: nested follow-up work created by an active turn module.
- `SimultaneousResolutionFrame`: all-required concurrent prompts and commits.

## Hard Rules

1. Draft prompts and draft events never mutate `turn_stage`.
2. Round-end card flip is legal only after every player turn module in the round frame is completed or skipped.
3. Resupply prompts use a simultaneous batch contract with `batch_id`.
4. Module prompt decisions must echo `resume_token`, `frame_id`, `module_id`, and `module_type`.
5. WebSocket replay may fill gaps only with projections compatible with the latest known runtime frame path.
6. Redis stores committed state atomically but does not replace backend semantic validation.
```

- [ ] **Step 2: Write round action matrix document**

Create `docs/runtime/round-action-control-matrix.md` using the table from section `0-2. Round Action Matrix`.

- [ ] **Step 3: Commit docs**

```bash
git add docs/runtime/end-to-end-contract.md docs/runtime/round-action-control-matrix.md
git commit -m "docs: document runtime end-to-end contract"
```

## 3. Final Verification Gate

Run these commands from `/Users/sil/Workspace/project-mrn`:

```bash
PYTHONPATH=GPT pytest \
  GPT/test_runtime_module_contracts.py \
  GPT/test_runtime_sequence_modules.py \
  GPT/test_runtime_simultaneous_modules.py \
  GPT/test_runtime_round_modules.py \
  GPT/test_runtime_turn_modules.py \
  apps/server/tests/test_runtime_semantic_guard.py \
  apps/server/tests/test_runtime_end_to_end_contract.py \
  apps/server/tests/test_prompt_module_continuation.py \
  apps/server/tests/test_view_state_turn_selector.py \
  apps/server/tests/test_view_state_runtime_projection.py \
  apps/server/tests/test_stream_service.py \
  -q
```

```bash
cd apps/web
npm test -- \
  src/domain/selectors/promptSelectors.spec.ts \
  src/domain/selectors/streamSelectors.spec.ts \
  src/domain/store/gameStreamReducer.spec.ts
```

Expected final result:

- Engine rejects impossible module placements.
- Backend rejects impossible stream/checkpoint payloads before Redis persistence.
- Prompt decisions cannot resume the wrong module type.
- Draft/final prompts never pollute prior turn progress.
- Round-end card flip never appears as a turn-middle action.
- Resupply uses simultaneous batch contract.
- Frontend does not fast-forward to stale projected runtime paths.

## 4. Self-Review

### 4-1. Spec Coverage

- Engine progression sections are covered by Tasks 1 and 2.
- Backend/Redis semantic limits are covered by Tasks 3 and 4.
- Projection and frontend visibility are covered by Tasks 5, 6, and 7.
- Verification is covered by Task 8 and the final verification gate.
- Documentation is covered by Task 9.

### 4-2. Placeholder Scan

This plan avoids implementation placeholders by naming exact files, test cases, guard functions, commands, and expected outcomes.

### 4-3. Type Consistency

The continuation field names are:

- Backend payload: `resume_token`, `frame_id`, `module_id`, `module_type`, `batch_id`
- Frontend view model: `resumeToken`, `frameId`, `moduleId`, `moduleType`, `batchId`
- Outbound WebSocket message: `resume_token`, `frame_id`, `module_id`, `module_type`, `batch_id`

The runtime frame names are consistently:

- `round`
- `turn`
- `sequence`
- `simultaneous`
