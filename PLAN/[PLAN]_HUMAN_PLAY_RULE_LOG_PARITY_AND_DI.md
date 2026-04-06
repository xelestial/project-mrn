# [PLAN] Human Play Rule/Log Parity And DI Injection Path

Status: ACTIVE  
Updated: 2026-04-05  
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

### 2026-04-05 spectator continuity checkpoint

- Completed:
  - `uiText.ts` was rebuilt as a UTF-8 resource catalog again.
  - non-local turn waiting state now uses `SpectatorTurnPanel` instead of a bare spinner-only waiting card.
  - the spectator panel now keeps weather / current beat / latest public action / move / landing / economy / effect / progress visible while another player is acting.
- Remaining:
  - prompt surfaces still contain leftover inline broken strings and legacy inspector phrasing
  - browser parity still needs an explicit non-local-turn spectator assertion, not only board/theater shell assertions
  - the main browser parity suite is green again after the UTF-8 catalog rebuild (`e2e/parity.spec.ts`)

### 2026-04-05 locale-boundary follow-up

- The next active slice is no longer "add i18n foundation".
- That foundation already exists and is in active use.
- Current parity risk now comes from selector-owned wording and bridge-owned fallback text:
  - `apps/web/src/domain/selectors/streamSelectors.ts`
  - `apps/web/src/domain/text/uiText.ts`
- Therefore the immediate execution order for this plan is:
  1. reduce selector ownership of visible phrases
  2. keep prompt/theater/stage continuity on top of locale resources
  3. continue browser parity checks for `1 human + 3 AI`
 - Dedicated browser recovery coverage now also exists in:
   - `apps/web/e2e/human_play_runtime.spec.ts`
 - That coverage currently locks:
   - quick start -> first local prompt visible
   - remote actor turn -> spectator panel visible and no local prompt

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

## 2026-04-07 Current Slice Closure Note

- Repo-side human-play parity work is now closed enough for the current slice:
  - mixed-seat browser/runtime coverage now keeps:
    - local prompt visibility
    - remote-turn spectator continuity
    - weather / fortune / purchase / rent / lap-reward visibility
    - external worker success/fallback continuity
    - readiness / attempt-limit / worker provenance visibility
  - current-turn stage and spectator panels now keep external-worker status inside the same scene/payoff flow rather than a detached debug lane
  - canonical decision context is now surfaced through selector/stage rendering strongly enough for local playtests
- Remaining work for this plan is now split:
  1. evidence-only UI drift cleanup if a real playtest shows a specific narrative problem
  2. future architecture work for behavior-provider DI around mark/weather/fortune
- That second item is intentionally not a blocker for the current playable mixed-seat runtime slice.
- Current visible state already includes:
  - latest core/public action surfaced as a hero card
  - lane cards with clearer hierarchy and emphasis
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

## 2026-04-05 Turn-Stage Continuity Update

- `selectTurnStage` now carries a live current-beat projection instead of only static sub-summaries.
  - latest core/public action in the current turn is projected as `currentBeatLabel` / `currentBeatDetail`
  - turn-start is now explicitly seeded into the visible progress trail
  - local blocking prompts can temporarily own the beat headline without mutating the underlying core summaries
- `TurnStagePanel` now surfaces:
  - actor hero
  - weather card
  - character card
  - current-beat card
  - progress-trail card
- This improves readability, but it still does not finish P0-2.
- Remaining parity work still includes:
  - richer visual distinction between movement / purchase / fortune / rent / turn-end beats
  - stronger board-side coupling between move destination and turn-theater beat
  - prompt choreography that feels fully live-play native instead of primarily inspector-style

## 2026-04-05 Browser Quick-Start Smoke Lock

- Added a browser-level smoke path for `1 human + 3 AI` quick start.
- The browser test now verifies:
  - session creation
  - human seat join
  - session start
  - match navigation
  - first human prompt visibility
  - weather/character text presence in the live match shell
- This does not finish P0-2.
- Remaining parity gaps are still mostly experiential:
  - movement prompt still needs stronger game-like choreography
  - prompt overlays still need to feel less like inspectors and more like live decision surfaces
  - other-player movement / purchase / fortune beats still need more motion and stronger continuity

## 2026-04-05 Prompt Surface Recovery Update

- The live React human-play prompt layer now covers the first major decision surfaces with dedicated browser checks:
  - `movement`
    - runtime-contract `dice_*` choice ids are now parsed correctly by the web prompt layer
    - card-mode selection is browser-tested
  - `purchase_tile`
    - decision cards now render with current tile / cost / cash / zone summaries
  - `mark_target`
    - target prompts now keep explicit `대상 인물 / 플레이어` wording in dedicated target cards
- This improves P0-2, but still does not finish it.
- Remaining visible parity work still includes:
  - actor-start -> move -> landing -> economy/result continuity for other-player turns
  - stronger board-side emphasis/motion when movement, purchase, fortune, and rent resolve
  - weather / fortune persistence that feels like live board state, not only prompt/local-card context

## 2026-04-05 Board/Stage Coupling Update

- The live React client now projects turn-beat metadata far enough to let the board and turn-stage point at the same public event:
  - `selectTurnStage` now carries:
    - `currentBeatKind`
    - `focusTileIndex`
  - those values are derived from canonical payload fields, not from ad-hoc UI-only state
- `BoardPanel` now uses that turn-stage focus to render:
  - a live board focus summary
  - tile emphasis by beat kind (`move / economy / effect / decision`)
- `TurnStagePanel` hero/current-beat cards now also shift emphasis by beat kind, so the board and stage no longer feel visually disconnected.
- Selector parity also improved for public economic beats:
  - `rent_paid` summaries are no longer blank
  - `fortune_drawn` / `fortune_resolved` now emit explicit summary strings through shared text resources
- This still does not finish P0-2.
- Remaining visible parity work still includes:
  - stronger continuity between actor start -> move -> landing -> result cards for non-local turns
  - weather / fortune persistence as a more anchored match-surface component
  - prompt choreography that feels like a live board game surface instead of a large inspector block

## 2026-04-05 Focused-Tile Readability Follow-up

- The board now shows a short live action tag directly on the focused tile, not only in the stage summary.
- `turn_start` summaries also no longer collapse into blank detail lines, which helps the first beat of a turn feel intentional instead of empty.
- This improves readability, but it still does not finish P0-2.
- Remaining visible parity work still includes:
  - stronger continuity between turn-start and the first public action card
  - more persistent weather / fortune anchoring in the match shell
  - reducing the remaining inspector/debug feel during long prompt-heavy turns

## 2026-04-05 Turn-Flow Surface Follow-up

- The live React client now exposes the latest public turn as a short ordered flow inside the theater panel instead of only showing disconnected recent cards.
- The board also now keeps the current round weather visible inside the board surface itself, not only in the turn-stage summary.
- Browser parity smoke now verifies both:
  - `board-weather-summary`
  - `core-action-flow-panel`
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger motion/choreography so the scene feels live rather than statically updated
  - fuller other-player turn storytelling around movement -> landing -> result
  - prompt surfaces that feel more like game actions than inspector panels

## 2026-04-05 Prompt/Spectator Surface Follow-up

- The local prompt overlay is now split into:
  - instruction/header
  - choice body
  - low-priority request metadata footer
- This change is intentionally aimed at removing the lingering "inspector panel" feel from human decisions.
- Remote-turn viewing also now exposes:
  - current weather
  - current weather effect
  - current character
  - current beat
  - latest public action
- Browser regression now locks the spectator character card as part of the remote-turn continuity contract.
- This still does not finish P0-2.
- Remaining visible parity work still includes:
  - stronger animated scene transitions for movement -> landing -> result
  - better anchoring of fortune/weather as long-lived scene elements during the whole turn
  - further shrinking of low-value metadata and raw-debug affordances in the human-play shell

## 2026-04-05 Top-Shell / Passive Guidance Follow-up

- The match top shell is now treated more like a compact HUD than a diagnostic strip:
  - connection data is rendered as small status cards
  - sticky top chrome is visually quieter
- Passive waiting state for other players' choices now uses a dedicated observer card instead of plain paragraph text.
- This improves readability for human players because the page no longer competes as strongly with:
  - the board
  - the turn stage
  - the theater flow
- This still does not finish P0-2.
- Remaining visible parity work still includes:
  - reducing or compartmentalizing the raw/debug surface even further
  - making the board scene itself feel more alive during other-player turns
  - stronger choreography around movement -> landing -> purchase/rent/fortune resolution

## 2026-04-05 Observer Continuity Follow-up

- The spectator surface now also exposes:
  - current weather effect
  - current prompt / decision state
- This means a remote turn is less likely to feel "frozen" in the gaps between public actions.
- Browser parity now locks:
  - spectator weather card
  - spectator character card
  - spectator prompt card
- This still does not finish P0-2.
- Remaining visible parity work still includes:
  - stronger board-space animation and arrival emphasis
  - making fortune / purchase / rent resolution feel like scene beats rather than static card swaps
  - removing more of the remaining raw/debug-first mental model from the match shell

## 2026-04-05 Board Focus Follow-up

- The board focus tile now exposes both:
  - the current beat label
  - the current beat detail
- Focused tiles also now pulse by beat kind so the board itself carries more of the live-scene explanation burden.
- This improves the "log replay" problem because the viewer no longer has to read only side panels to understand why a tile is currently important.
- This still does not finish P0-2.
- Remaining visible parity work still includes:
  - stronger pawn/path animation rather than only highlighted arrival/focus states
  - better scene presentation for fortune / rent / purchase resolution
  - further reducing raw/debug prominence from the main match shell

## 2026-04-05 Board Actor / Move Marker Follow-up

- The board now explicitly marks movement continuity in-scene with:
  - `출발 / 도착` tile badges
  - an active-turn actor banner on the currently relevant tile
  - stronger pulse emphasis for the active pawn
- These markers are locale-backed instead of hardcoded in the component, so the same scene can later switch language without re-editing the board surface.
- Browser regression now locks:
  - `board-move-start-badge`
  - `board-move-end-badge`
  - `board-actor-banner`
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - path-like movement animation rather than only origin/destination emphasis
  - more theatrical fortune / rent / purchase result presentation
  - continued reduction of residual debug/inspector affordances from the match shell

## 2026-04-05 Movement / Mark Prompt Follow-up

- The movement prompt is now intentionally flatter and more game-like:
  - compact current context
  - mode tabs
  - selected-state pills
  - one clear execute button
- The mark-target prompt now exposes target identity directly as choice pills:
  - target character
  - target player id
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger per-event scene choreography for fortune / rent / purchase
  - more reduction of leftover inspector-like metadata in prompt surfaces
  - fuller remote-turn storytelling so non-local turns feel less like card swaps

## 2026-04-05 Public Turn-Flow Journey Follow-up

- The public action panel now exposes the latest same-turn public beats as a compact journey strip.
- This is intentionally separate from the feed grid so a human observer can read:
  - what happened first
  - what followed
  - what the current public beat is
  without reconstructing that order from disconnected cards.
- Browser regression now locks `core-action-journey` for remote-turn continuity.
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger fortune / purchase / rent result staging
  - more persistent scene anchoring during long remote turns
  - additional reduction of raw/debug mental-model cues in the match shell

## 2026-04-05 English Runtime Safety Mode

- Runtime validation is temporarily anchored to English boot mode.
- Reason:
  - Korean locale recovery is still in progress
  - human-play runtime work must continue on a stable language baseline instead of blocking on locale repair
- Current rule:
  - `apps/web` should boot in English by default
  - selector/build/browser parity must remain green in English mode
  - Korean locale repair should proceed as a separate controlled track under P0-4
- This does not change the long-term bilingual goal.
- It is only the current stabilization baseline while P0-2 human-play recovery continues.

## 2026-04-05 Prompt Readability / Scene Continuity Follow-up

- English-mode prompt surfaces were cleaned further so they read less like raw inspector cards:
  - bracket-heavy wording was removed from visible trick / character / mark copy
  - request meta now prioritizes actor + time left instead of exposing request ids first
  - corrupted unit suffixes were removed from movement / mark / purchase / lap-reward context cards
- The movement prompt now shows dice-card chips as plain card numbers instead of bracket-wrapped debug tokens.
- Turn-stage scene continuity was extended:
  - move
  - landing
  - purchase
  - rent
  - fortune
  now all appear in the scene strip when available
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger pawn/path animation instead of only scene-card continuity
  - more theatrical resolution treatment for fortune / purchase / rent beats
  - additional reduction of residual inspector/debug affordances from prompt and side panels

## 2026-04-06 Theater De-duplication / Spectator Readability Follow-up

- The public-action theater now avoids rendering the same turn flow twice.
  - `CoreActionPanel` keeps:
    - latest hero action
    - same-turn journey strip
    - older public action feed
  - the extra duplicate flow panel was removed
- Browser parity now anchors on `core-action-panel` itself for early-turn states where a journey strip is not guaranteed yet.
- Spectator readability was raised:
  - current beat title/detail are now separated
  - latest public action title/detail are now separated
  - economy/effect summaries are normalized through shared join logic instead of ad-hoc slash packing
- English prompt copy was softened again so prompt surfaces read less like transport/debug UI:
  - lighter request meta
  - cleaner collapsed chip wording
  - cleaner movement/trick/mark/purchase copy
  - simpler busy-state wording
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger pawn/path animation instead of only tile emphasis
  - more theatrical fortune / purchase / rent result staging
  - further reduction of residual prompt metadata weight in non-English locale recovery

## 2026-04-06 Prompt HUD Timing Follow-up

- Actionable prompt surfaces now expose countdown pressure with a live timer bar in addition to the metadata pill.
- This intentionally shifts the prompt footer from:
  - transport/debug text
  toward:
  - game HUD timing
  - actor awareness
  - immediate urgency cue
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger pawn/path animation instead of only tile emphasis
  - more theatrical fortune / purchase / rent result staging
  - continued cleanup of residual non-English prompt metadata weight during KO recovery

## 2026-04-06 Weather Effect Payload Parity Follow-up

- Weather summaries in the live React selectors now explicitly honor `weather_reveal.effect_text` when provided by the runtime.
- This closes one visible parity gap where the UI could otherwise fall back to:
  - generic weather effect labels
  instead of:
  - the actual rule text supplied by the runtime
- Selector coverage was added so this does not silently regress.
- This improves P0-3, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger pawn/path animation instead of only tile emphasis
  - more theatrical fortune / purchase / rent result staging
  - continued cleanup of residual non-English prompt metadata weight during KO recovery

## 2026-04-06 AI Decision-Lane Noise Follow-up

- Server runtime now emits AI-seat decision lifecycle events through the same canonical contract used by human seats.
- To keep human-play readability intact:
  - React selector lane routing now treats `provider="ai"` decision lifecycle events as `system` lane, not `prompt` lane.
- Result:
  - auditability improved
  - local human prompt UX remains protected from new AI decision chatter
- Remaining parity work still includes:
  - stronger turn scene continuity during remote actions
  - more theatrical purchase / rent / fortune presentation
  - eventual typed provider/port migration so runtime wrapper logic does not stay concentrated in one bridge class

## 2026-04-06 Remote-Turn Move Path Follow-up

- Remote-turn continuity now preserves the latest emitted move path, not only move origin/destination.
- React selectors now retain `player_move.path` as recent move state.
- The board now renders intermediate path-step badges so observers can read:
  - where the actor started
  - which tiles the route passed through
  - where the actor arrived
- Browser parity now locks at least one intermediate path step for remote-turn continuity.
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger pawn/path animation instead of static path-step badges only
  - more theatrical fortune / purchase / rent staging after the route completes
  - continued prompt-surface cleanup so local choices feel less like an inspector

## 2026-04-06 Ordered Turn-Journey Follow-up

- The turn-stage scene strip now includes prompt/decision state in the same ordered lane as:
  - move
  - landing
  - purchase
  - rent
  - fortune
- Scene steps are now explicitly numbered, so observers can read the turn as a sequence instead of a loose group of cards.
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger pawn/path animation instead of static emphasis only
  - more theatrical fortune / purchase / rent resolution cards
  - continued cleanup of residual prompt metadata weight

## 2026-04-06 Outcome-Card Staging Follow-up

- The live React client now gives purchase / rent / fortune / trick outcomes their own dedicated scene surfaces:
  - `TurnStagePanel` now exposes a dedicated outcome strip
  - `SpectatorTurnPanel` now exposes a spotlight row for public economy/effect outcomes
  - `CoreActionPanel` now exposes a dedicated latest-result card for economy/effect beats
- Prompt HUD wording was also shortened again at the component layer so collapsed/local prompt state reads less like transport metadata.
- Browser parity now explicitly locks:
  - `spectator-turn-spotlight`
  - `core-action-result-card`
  - `turn-stage-outcome-strip`
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger pawn/path animation instead of static path badges and pulse only
  - fuller live fortune / weather reveal treatment as scene beats, not only summary cards
  - more reduction of residual inspector feel in movement / reward / mark prompt surfaces

## 2026-04-06 Move-Trail Wave Follow-up

- The board now gives recent move-path tiles a staggered pulse instead of only a static badge.
- `BoardPanel` now passes path-step order through to CSS.
- `styles.css` now animates:
  - intermediate move-trail tiles
  - path-step badges
  with step-based delays so the route reads left-to-right / start-to-end more naturally.
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - true pawn interpolation or equivalent stronger route animation
  - fuller fortune / weather reveal staging as dedicated scene beats
  - continued simplification of movement / reward / target prompt surfaces

## 2026-04-06 Weather / Fortune Spotlight Follow-up

- The live React client now gives weather / fortune / economy outcomes a stronger in-scene presence:
  - `TurnStagePanel` now exposes a dedicated spotlight strip above the lower summary cards
  - `SpectatorTurnPanel` now starts with a hero scene card instead of only a flat card grid
- The movement prompt was also flattened again:
  - removed the old context-card block
  - kept the same information as compact summary pills
  - removed one remaining hardcoded Korean roll-title check from prompt choice parsing
- The match shell now reduces debug prominence further:
  - the raw/debug toggle no longer stays in the always-visible top command row
  - it only appears after expanding the top runtime/connection section
- Browser parity now explicitly locks:
  - `spectator-turn-scene`
  - `turn-stage-spotlight-strip`
  - hidden raw/debug toggle by default in match mode
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - true pawn interpolation or equivalent stronger route animation
  - fuller fortune-card / fortune-resolution staging beyond text spotlight only
  - further simplification of remaining reward / mark prompt surfaces

## 2026-04-06 Prompt Flattening Follow-up

- Major human prompt surfaces now favor summary pills over small diagnostic-looking context cards:
  - movement
  - mark target
  - purchase
  - lap reward
- The same state is still visible, but the prompt now reads more like:
  - what matters now
  - what you can choose now
  rather than:
  - a stack of context/debug panels
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - true pawn interpolation or equivalent stronger route animation
  - fuller fortune-card / fortune-resolution staging beyond text spotlight only
  - additional cleanup for any remaining inspector-like surfaces in non-movement prompts

## 2026-04-06 Ghost-Pawn Travel Follow-up

- The board now renders a transient ghost pawn travel overlay between the latest move start and move end.
- This sits on top of:
  - move-start badge
  - move-end badge
  - intermediate path-step badges
  so remote turns now read more like a moving piece and less like only a highlighted log snapshot.
- Browser parity now explicitly locks:
  - `board-moving-pawn-ghost`
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - richer per-step pawn interpolation instead of one start-to-end travel ghost only
  - stronger fortune / rent / purchase payoff cards and transitions
  - continued simplification of the remaining prompt surfaces so they read like live game UI instead of selection inspectors

## 2026-04-06 Payoff / Prompt Follow-up

- Remote-turn scene payoff was raised another step:
  - spectator spotlight cards now label outcomes specifically as:
    - purchase
    - rent
    - fortune
    - trick
    instead of collapsing them into generic economy/effect buckets
  - the spectator hero scene card now combines:
    - latest public action headline
    - current beat detail
    so other-player turns read more like a continuing scene
- Movement prompt clutter was reduced again:
  - current-position and weather remain visible
  - selected-card state only appears when the player is actually in card-selection mode
  - the generic usable-card count moved out of the always-on summary row
- Canonical event summaries were also strengthened for live UX:
  - tile purchase details now include the acting player
  - lap reward details now include the acting player
  - fortune draw / resolution details now include the acting player
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - fuller fortune/weather reveal staging as dedicated scene beats, not only summary cards
  - purchase/rent outcome transitions that feel more like board-game events than feed entries
  - more reduction of inspector feel in mark/reward/special prompts

## 2026-04-06 Human-Playable Guardrail Follow-up

- Spectator payoff is now part of the protected browser contract, not just an incidental card in the panel.
- Locale switching persistence is now also protected because live human-play verification needs stable bilingual switching without reload drift.
- Remaining visible parity work still includes:
  - fuller fortune/weather reveal staging as dedicated scene beats, not only summary cards
  - purchase/rent outcome transitions that feel more like board-game events than feed entries
  - more reduction of inspector feel in mark/reward/special prompts

## 2026-04-06 Spectator Journey Follow-up

- Remote-turn continuity now also includes a dedicated spectator journey strip.
- The strip currently sequences:
  - character
  - current prompt/choice beat
  - movement
  - landing
  - economy/effect payoff
- Prompt display order also now pushes passive `none`/skip-style entries to the end so action-first reading is preserved.
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger fortune/weather reveal staging as dedicated scene beats
  - purchase/rent outcome transitions that feel more animated than feed-like
  - additional simplification for mark/reward/special prompts that still read too much like inspectors

## 2026-04-06 Spectator Result Follow-up

- Remote-turn continuity now keeps a dedicated spectator result/payoff card in addition to:
  - spotlight cards
  - journey strip
  - progress trail
- Prompt chrome also moved request meta upward into the head area so the footer no longer reads like a debug/control bar.
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger fortune/weather reveal staging as dedicated scene beats
  - more animated purchase/rent outcome transitions
  - final prompt simplification for a few specialty flows

## 2026-04-06 Weather / Specialty Prompt Follow-up

- Remote-turn weather is now also part of the spectator spotlight strip instead of only a small static status card.
- Spectator journey continuity now sequences:
  - character
  - current choice
  - movement
  - landing
  - purchase
  - rent
  - fortune
  where those beats are available, instead of collapsing all outcomes into one generic economy/effect step.
- `TurnStagePanel` now keeps weather in the scene strip and can surface weather effect as an outcome beat when no stronger fortune outcome is active.
- Remaining specialty prompt surfaces now have dedicated layouts for:
  - `active_flip`
  - `burden_exchange`
  - `specific_trick_reward`
  so they no longer fall back to the generic inspector-style grid.
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger fortune reveal staging as a dedicated scene beat, not only a summary/result card
  - more animated purchase/rent outcome transitions
  - continued reduction of inspector feel in a few remaining generic/secondary prompt states

## 2026-04-06 Remaining Generic Prompt Split Follow-up

- The remaining secondary prompt families no longer use the plain generic choice grid:
  - `runaway_step_choice`
  - `coin_placement`
  - `doctrine_relief`
  - `geo_bonus`
- They now render on the same emphasized live-choice surface used by the stronger prompt types, with context pills where available.
- Spectator remote-turn continuity now also begins with a weather beat in the journey strip, so the public flow reads more like:
  - weather
  - character
  - current choice
  - movement
  - landing
  - payoff
- This improves P0-2, but it still does not finish it.
- Remaining visible parity work still includes:
  - stronger fortune reveal staging as a dedicated scene beat, not only summary/result text
  - richer purchase/rent payoff transitions so outcomes feel more like board-game events
  - further simplification for any still-generic fallback prompts such as rare/late specialty paths
