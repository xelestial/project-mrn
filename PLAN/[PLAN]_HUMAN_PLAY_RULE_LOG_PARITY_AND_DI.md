# [PLAN] Human Play Rule/Log Parity And DI Injection Path

Status: ACTIVE  
Updated: 2026-04-04  
Owner: GPT

## 1) Current Assessment

### 1.1 Are engine rule version and log order fully reflected in human play?
Short answer: NOT FULLY.

Observed from code:
- Runtime path uses the same engine (`GPT/engine.py`) for AI-only and human-mixed sessions via:
  - `apps/server/src/services/runtime_service.py`
  - `_ServerHumanPolicyBridge` + `_FanoutVisEventStream`
- So core rule execution order in engine is shared.
- However, human play stream is mixed:
  - engine `event` messages
  - `prompt` messages
  - `decision_ack` messages
  - `error` messages (watchdog/runtime)
- Frontend summaries/selectors still include hardcoded and lossy interpretations, so user-visible flow can diverge from true engine sequence.

Conclusion:
- Engine-side order: largely shared.
- Human-play visible order/UX order: not guaranteed to match game rule narrative end-to-end.

### 1.2 Are mark/fortune/weather DI-injected as swappable modules?
Short answer: PARTIAL ONLY.

Current state:
- Parameter DI exists for session/runtime/base values:
  - seats, board topology, dice values, starting cash/shards, labels
  - `apps/server/src/services/parameter_service.py`
  - `apps/server/src/services/engine_config_factory.py`
- But behavior-level DI for mark/fortune/weather is not fully abstracted:
  - engine/effect handlers still contain hardcoded behavior and card-name branching
  - `GPT/effect_handlers.py`, `GPT/engine.py`
- `RuleScriptEngine` exists but covers only limited hooks:
  - `GPT/rule_script_engine.py` (`landing.f.resolve`, `fortune.cleanup.resolve`, `game.end.evaluate`)
  - not a full replacement for mark/weather/fortune behavior providers

Conclusion:
- Current architecture is config-driven, not fully behavior-injected.
- Additional DI boundary work is required.

## 2) Gap Matrix

### G1. Rule narrative vs UI rendering
- Risk:
  - Human viewer can feel like a replay/debug feed, not authoritative live game UX.
- Cause:
  - Frontend relies on selector-level inferred summaries and hardcoded labels.
- Primary files:
  - `apps/web/src/domain/selectors/streamSelectors.ts`
  - `apps/web/src/features/prompt/PromptOverlay.tsx`
  - `apps/web/src/App.tsx`

### G2. Log/stream ordering perception mismatch
- Risk:
  - Users perceive wrong sequence even when engine is correct.
- Cause:
  - Prompt/ack/error mixed with core events in one visual lane.
- Primary files:
  - `apps/server/src/services/runtime_service.py`
  - `apps/web/src/domain/selectors/streamSelectors.ts`

### G3. DI boundary incomplete for mark/weather/fortune
- Risk:
  - Rule updates require touching engine internals and UI glue together.
- Cause:
  - Behavior logic still embedded in engine/effect handlers.
- Primary files:
  - `GPT/effect_handlers.py`
  - `GPT/engine.py`
  - `GPT/rule_script_engine.py`

## 3) Execution Plan

## P0 (Blockers, must finish first)

1. Freeze canonical ordering contract for human play rendering
- Add a strict event lane contract:
  - Core lane: `round_start -> weather_reveal -> draft_* -> turn_start -> trick_used? -> dice_roll -> player_move -> landing_resolved -> ... -> turn_end_snapshot`
  - Prompt lane: `prompt`, `decision_ack`
  - System lane: runtime watchdog/error
- Deliverables:
  - docs update + selector test fixtures for sequence
- Files:
  - `docs/backend/log-engine-generation-audit.md`
  - `apps/web/src/domain/selectors/streamSelectors.ts`
  - `apps/web/src/domain/selectors/*.spec.ts`

2. Human-play parity smoke test pipeline
- Add automated checks for 1 human + 3 AI session:
  - prompt appears
  - submit accepted
  - core turn events keep order
  - weather/fortune/mark visible in correct lane
- Files:
  - `apps/server/tests/test_runtime_service.py`
  - `apps/web/e2e/*` (or existing integration harness)

## P1 (Rule parity in visible UX)

1. Turn theater split rendering
- Separate three tracks in UI:
  - Rule progression track (core events only)
  - Prompt/decision track
  - System warning/error track
- Prevent watchdog warning from replacing main game narrative card.

2. Event-first summary model
- For weather/fortune/mark, render from canonical payload fields only.
- Remove selector guessing where payload already has authoritative fields.

3. Prompt visibility policy
- Only actionable prompt blocks input.
- Non-actionable prompts become compact observer card, not modal blocker.

## P2 (DI completion path for mark/weather/fortune)

1. Introduce behavior provider interfaces
- `WeatherEffectProvider`
- `FortuneEffectProvider`
- `MarkResolutionProvider`

2. Wire providers through engine config factory
- Server resolves provider profile from parameters.
- Engine receives provider adapters, not direct hardcoded branching.

3. Expand rule script/registry scope
- Either:
  - extend `RuleScriptEngine` event coverage, or
  - implement provider registry with explicit typed actions.
- Keep deterministic behavior and test snapshots.

## P3 (Regression shield)

1. Add “no resurrection” checklist for previously reported UX bugs
- Maintain a tracked regression list in PLAN/docs.
- Every PR touching runtime/web must run checklist.

2. Add sequence/property tests
- Monotonic `seq`
- turn phase ordering invariants
- prompt lifecycle invariant (`open -> ack(stale/rejected/accepted) -> close`)

## 4) Definition Of Done

- Human session (1 human + 3 AI) shows same core rule sequence as engine logs.
- Weather/fortune/mark display in dedicated, stable core event lane.
- Prompt/decision/system messages no longer scramble turn narrative.
- Mark/weather/fortune behavior routing is provider-based (DI) and test-covered.
- Rule change in source config/provider does not require frontend hardcoded patch.

## 5) Notes For Immediate Next Work

First implementation slice:
1. P0-1 contract freeze (docs + selector tests)
2. P0-2 human mixed-session automated smoke
3. P1-1 lane split UI rendering

This order is chosen to stop further drift before additional feature edits.

## 2026-04-05 Progress Note

- Selector-side narrative drift was reduced in the live React client:
  - resolved passive prompts now close from canonical decision events, not only from local `decision_ack`
  - `현재 상황` headline now ignores prompt/system chatter and follows core turn narrative instead
- This does not finish P0-2 yet.
- Remaining visible parity gaps still include:
  - distinct rendering of other-player turn actions as theater-grade cards
  - observer prompt cards vs blocking local prompt separation at full-screen layout level
  - weather/fortune/mark persistence and actor-stage continuity in the main match screen

## 2026-04-05 Additional Progress Note

- Added a dedicated public-action lane to the live React match screen.
  - latest visible non-local/public action now appears as a hero card
  - recent public actions appear in a short card feed beneath it
  - legacy duplicated strip/banner UI is hidden so the core lane has a single entry point
- Began viewport-scale layout recovery:
  - desktop side column now stays sticky
  - board square scales from viewport constraints instead of a hard `980px` cap
  - prompt overlay now opens near full viewport size
- Prompt presentation started separating further from public-action playback:
  - prompt overlay is now request-type aware via CSS classing
  - bottom-sheet style placement reduces total board occlusion
  - choice density differs by prompt type instead of one uniform card wall
- Turn-theater readability was raised:
  - theater panel is now labeled in player-facing Korean
  - latest core/public action is surfaced as a hero card
  - lane cards have clearer hierarchy and emphasis
- Stage summary readability was also raised:
  - current actor turn summary is now a hero card
  - weather remains visible in its own card
  - movement / landing / card effect summaries are separated instead of mixed together
- Board pawn readability improved:
  - pawn tokens now render player numbers directly inside the token
- Public-action classification improved:
  - rent / fortune now render in the same economic/public-action tone family
  - trick usage is promoted for stronger visibility in theater cards
- Public-action cards now also expose lightweight category chips:
  - `이동 / 경제 / 효과 / 선택 / 진행`
  - this improves scanability before full per-event bespoke card rendering lands
- Theater components were re-saved in clean UTF-8 Korean and re-stabilized:
  - `CoreActionPanel`
  - `IncidentCardStack`
- Legacy duplicate public-action rendering in `App.tsx` is now disabled at runtime so only the new action lanes are visible.
- This is still only a first UI slice.
- Remaining parity work:
  - stronger motion/readability treatment for movement, purchase, fortune, rent, and turn-end beats
  - viewport-filling layout recovery
  - prompt placement separation so local decisions do not feel like replay cards

## 2026-04-05 Follow-up Progress Note

- The remaining disabled legacy public-action JSX in `apps/web/src/App.tsx` has now been physically removed.
- Theater/UI differentiation was raised another step:
  - `CoreActionPanel` now renders distinct detail blocks per action family
  - `IncidentCardStack` now explains each lane (`turn progress / prompt flow / system log`) with subtitles
  - `TurnStagePanel` was re-centered around persistent weather / actor / movement / landing / card-effect summaries
- This still does not complete P0-2.
- Remaining visible parity gaps still include:
  - stronger continuity/motion between actor start -> move -> landing -> economy/result beats
  - richer other-player turn surfacing so the live view stops feeling like a replay/debug wall
  - prompt presentation that feels fully native to live play instead of a large inspector-style panel
