# 1_HUMAN_GAME_PIPELINES_AND_RUNTIME_REFERENCE

Status: ACTIVE  
Audience: Human readers  
Updated: 2026-04-14

This file is written for humans.

Its purpose is to explain the runtime in plain language, with enough file-level detail to navigate the codebase safely.

## 1. System Overview

The online game runtime has three main layers:

1. engine
2. backend runtime and selector middleware
3. frontend renderer

The engine decides gameplay truth.  
The backend transports and derives stable public view-state.  
The frontend should render that view-state and animate it.

## 2. Main Pipelines

### 2.1 Core gameplay event pipeline

Flow:

1. engine computes state transition
2. engine emits visual event payload
3. backend stream service stores ordered message with `seq`
4. backend view-state projector derives additive `view_state`
5. frontend selectors read raw payload plus backend projection
6. React components render HUD, prompt, board, and theater state

Primary files:

- `GPT/engine.py`
- `GPT/effect_handlers.py`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/stream_service.py`
- `apps/server/src/domain/view_state/projector.py`
- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/App.tsx`

### 2.2 Human decision prompt pipeline

Flow:

1. engine calls decision policy bridge
2. backend decision gateway builds prompt contract
3. prompt service stores pending prompt
4. stream publishes prompt envelope
5. backend projector adds prompt-facing `view_state`
6. frontend prompt selectors convert payload to prompt view model
7. user submits choice
8. backend validates and forwards choice back to runtime

Primary files:

- `apps/server/src/services/decision_gateway.py`
- `apps/server/src/services/prompt_service.py`
- `apps/server/src/routes/prompts.py`
- `apps/web/src/domain/selectors/promptSelectors.ts`
- `apps/web/src/App.tsx`

### 2.3 Active character / mark-target / role-strip pipeline

Flow:

1. engine determines `active_by_card`
2. engine or backend start events publish `active_by_card`
3. backend player selector turns `active_by_card` into `active_slots`
4. frontend reads `active_slots` for:
   - current active character strip
   - player face labels
   - mark-target prompt candidates
5. before stream hydration completes, frontend may seed the strip from session REST field `initial_active_by_card`

Primary files:

- `GPT/engine.py`
- `GPT/viewer/public_state.py`
- `apps/server/src/routes/sessions.py`
- `apps/server/src/domain/view_state/player_selector.py`
- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/domain/manifest/manifestRehydrate.ts`

### 2.4 Weather / fortune / trick display pipeline

Flow:

1. engine requests effect execution through the event bus for gameplay effects such as round weather
2. default effect handlers apply gameplay state changes
3. engine emits domain event such as `weather_reveal`, `fortune_drawn`, `trick_used`
4. backend reveal and scene selectors derive public situation fields
5. frontend renders those public fields in weather, theater, prompt, and board HUD

Primary files:

- `GPT/engine.py`
- `GPT/event_system.py`
- `GPT/effect_handlers.py`
- `apps/server/src/domain/view_state/reveal_selector.py`
- `apps/server/src/domain/view_state/scene_selector.py`
- `apps/web/src/domain/selectors/streamSelectors.ts`

Important current note:

- `weather.round.apply` is now single-sourced through the event bus
- the earlier dead duplicate in `GPT/engine.py` has been removed
- as of the 2026-04-12 audit, the remaining default effect-handler registrations are all referenced by engine event emission paths

### 2.5 Animation pipeline

Current animation ownership is frontend-side.

Flow:

1. backend event stream delivers ordered visual events
2. frontend queue or hooks map event kinds into transient animation state
3. components consume that local animation state

Primary files:

- `apps/web/src/features/board/useEventQueue.ts`
- `apps/web/src/features/board/usePawnAnimation.ts`
- `apps/web/src/features/board/GameEventOverlay.tsx`
- `apps/web/src/App.tsx`

Important note:

- gameplay truth must not depend on animation completion
- animation should only decorate already-decided state

## 3. Important Files, Functions, And Parameter Rules

### Engine

- `GPT/engine.py`
  - `run()`
  - `_start_new_round(state, initial=False)`
  - `_take_turn(state, player)`
  - `_emit_vis(event_type, phase, player, state, **payload)`
  - `_apply_round_weather(state)` now acts as an event-bus wrapper, not a direct weather implementation
  - parameter rule: gameplay ids should be emitted as stable numbers or enums where possible

- `GPT/event_system.py`
  - `EventDispatcher.register(event_name, handler)`
  - `EventDispatcher.emit_first_non_none(event_name, *args, **kwargs)`
  - rule: engine effect entrypoints should dispatch through this layer when a handler path exists

- `GPT/effect_handlers.py`
  - `EngineEffectHandlers.register_default_handlers(dispatcher)`
  - `apply_round_weather(state)`
  - rule: effect logic should live here when the corresponding engine path is event-driven

### Backend runtime

- `apps/server/src/services/runtime_service.py`
  - `start_runtime(session_id, seed=42, policy_mode=None)`
  - rule: runtime boot must not invent gameplay truth outside engine output

- `apps/server/src/services/decision_gateway.py`
  - builds prompt payloads and public_context
  - rule: inject canonical ids and explicit public context instead of relying on title text

- `apps/server/src/services/stream_service.py`
  - `publish(session_id, msg_type, payload)`
  - `snapshot(session_id)`
  - rule: messages are ordered by additive `seq`

### Backend selectors

- `apps/server/src/domain/view_state/player_selector.py`
  - `build_player_view_state(messages)`
  - `build_active_slots_view_state(messages)`
  - `build_mark_target_view_state(messages)`

- `apps/server/src/domain/view_state/prompt_selector.py`
- `apps/server/src/domain/view_state/reveal_selector.py`
- `apps/server/src/domain/view_state/scene_selector.py`
- `apps/server/src/domain/view_state/projector.py`

Selector rule:

- selectors should consume stable payload ids and explicit context
- selectors should not infer gameplay truth from localized labels if a canonical field exists

### Frontend selectors

- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/domain/selectors/promptSelectors.ts`
- `apps/web/src/domain/manifest/manifestRehydrate.ts`

Current caution:

- these files still contain small fallback branches that read display text when canonical fields are missing
- canonical ids and structured metadata should remain the first-choice source of truth

## 4. Unit Tests And Validation Rules

### Engine and runtime

- `GPT/test_visual_runtime_substrate.py`
- `apps/server/tests/test_runtime_service.py`
- `apps/server/tests/test_sessions_api.py`
- `apps/server/tests/test_stream_api.py`

Validation rule:

- every startup, round-start, and prompt-critical event should keep enough data for backend selectors to derive stable public state
- whenever an engine method is converted to an event-bus wrapper, tests must prove:
  - the dispatcher path is actually used
  - the default handler still reproduces gameplay behavior
  - custom handler override remains possible

### Backend selectors

- `apps/server/tests/test_view_state_player_selector.py`
- `apps/server/tests/test_view_state_prompt_selector.py`
- `apps/server/tests/test_view_state_scene_selector.py`
- `apps/server/tests/test_view_state_reveal_selector.py`

Validation rule:

- selector output should be tested using raw stream message fixtures, not only direct helper calls

### Frontend selectors

- `apps/web/src/domain/selectors/streamSelectors.spec.ts`
- `apps/web/src/domain/selectors/promptSelectors.spec.ts`
- `apps/web/src/domain/characters/prioritySlots.spec.ts`
- `apps/web/src/domain/manifest/manifestRehydrate.spec.ts`
- `apps/web/src/domain/manifest/manifestReconnectFlow.spec.ts`

Validation rule:

- frontend selector tests should mirror backend projection shape and prompt payload shape
- frontend tests should not silently rely on translated label text as game logic input
- manifest tests should prove reconnect / replay merges preserve board, seats, dice, economy, and resources

### Browser runtime checks

- `apps/web/e2e/parity.spec.ts`
- `apps/web/e2e/human_play_runtime.spec.ts`
- `.github/workflows/frontend-browser-runtime-tests.yml`

Validation rule:

- browser runtime checks should prefer `data-testid` and `data-*` assertions over broad localized text blocks
- active strip, weather, prompt rows, and runtime theater are all expected to expose CI-visible structure

## 5. Gameplay Processing Order

Canonical high-level order:

1. session start
2. round start
3. weather reveal
4. draft and final character choice
5. turn start
6. trick phase
7. movement value resolution
8. player move
9. landing resolution
10. rent payment or purchase follow-ups
11. marker management
12. turn end snapshot
13. round end and next round preparation

Reference:

- `docs/current/backend/turn-structure-and-order-source-map.md`

## 6. Multiplayer Runtime Model

The multiplayer environment is mixed-seat.

That means:

- some seats may be human
- some seats may be local AI
- some seats may be external AI

Main rules:

- session service owns seat and token lifecycle
- runtime service owns one engine loop per session
- prompt service holds pending human prompts
- stream service distributes ordered events to all clients
- reconnecting clients rebuild state from replay, not from component-local memory

Primary files:

- `apps/server/src/services/session_service.py`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/prompt_service.py`
- `apps/server/src/services/stream_service.py`

## 7. API Summary

## 8. Dead-code And Convergence Notes

Human summary:

- Not every historical effect path was fully event-driven.
- Weather had drifted into a split state:
  - direct implementation in `GPT/engine.py`
  - registered-but-unused implementation in `GPT/effect_handlers.py`
- That split has been corrected.

Current rule of thumb:

- if an engine path calls `emit_first_non_none(...)`, the effect body should not also exist as a second independently maintained implementation in engine
- wrappers are acceptable
- duplicated gameplay branches are not

### REST

- `POST /api/v1/sessions`
- `GET /api/v1/sessions`
- `GET /api/v1/sessions/{session_id}`
- `POST /api/v1/sessions/{session_id}/join`
- `POST /api/v1/sessions/{session_id}/start`
- `GET /api/v1/sessions/{session_id}/replay`
- `GET /api/v1/sessions/{session_id}/runtime-status`

### WebSocket

- `WS /api/v1/sessions/{session_id}/stream`

### Payload expectations

- raw event payloads remain canonical
- additive `view_state` must be safe to consume directly
- prompts must include canonical ids where available
- session REST payloads should expose:
  - `parameter_manifest`
  - `initial_active_by_card`
- frontend bootstrap should not wait for the first prompt just to discover active faces
- UI labels should be presentation fields, not logic keys

Reference:

- `docs/current/api/online-game-api-spec.md`
- `docs/current/backend/online-game-interface-spec.md`

## 8. Dead-Code Audit Notes

This section records current evidence, not guesses.

### Frontend

Audit command:

- `cd apps/web && npm_config_cache=/tmp/npm-cache npx --yes ts-prune`

Result on 2026-04-12:

- no unused exported symbol list was reported

Interpretation:

- frontend dead code may still exist as internal locals or unreferenced branches
- but there is no immediate exported-symbol dead-code list from this pass

### Backend / GPT candidate scan

Audit command:

- `vulture apps/server/src GPT --min-confidence 80`

Candidate findings included:

- `GPT/ai_policy.py`
  - unused import at line 98
  - multiple unreachable branches after `return` or `raise`
- `GPT/engine.py`
  - one unreachable branch after `return`
- `GPT/test_policy_runtime_modules.py`
  - unused local variables in tests

Interpretation:

- these are candidate dead-code findings
- they require manual semantic review before removal
- they should not be mass-deleted blindly because policy and test files contain many intentional guard branches

### Confirmed non-functional junk

- `docs/.DS_Store`

This file is not meaningful project content and should be removed.

## 9. Stabilization Follow-Up Checklist

- replace name-based rule conditions with canonical ids
- reduce frontend selector fallback logic based on localized titles
- move more prompt and scene truth into backend selectors
- triage vulture findings into confirmed dead code vs intentional compatibility paths
- keep this document updated when a pipeline boundary changes
