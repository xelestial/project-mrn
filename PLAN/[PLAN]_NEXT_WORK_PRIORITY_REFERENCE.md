# [PLAN] Next Work Priority Reference

Status: ACTIVE  
Updated: 2026-04-07  
Owner: GPT

## Purpose

This is the daily execution board.

If multiple plans exist, this file decides:
- what is blocked now
- what is active now
- what should wait

Always read this after the mandatory principles document.

## P0. Immediate Execution

### P0-1. Unified Decision API Stability

Source plans:
- `PLAN/[PLAN]_UNIFIED_DECISION_API_ORCHESTRATION.md`
- `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`

Goal:
- keep one canonical decision flow for both AI and human seats

Must remain true:
- `decision_requested -> decision_resolved(or decision_timeout_fallback) -> domain events`
- prompt ownership is seat-correct
- replay/live ordering stays deterministic

Current focus:
- preserve ordering while refactoring prompt UI and locale architecture
- do not let UI-side wording changes reintroduce stale-prompt or wrong-seat regressions
- continue after the runtime-wrapper unification slice:
  - AI seats already emit canonical decision lifecycle events at the server boundary
  - timeout/ack stream paths now share canonical payload builders too
  - engine `choose_*` waves now run through the injected `DecisionPort`
  - the server bridge now accepts engine-style canonical requests directly
  - the current next step is to close the remaining contract/consumer gap:
    - frontend canonical prompt consumption beyond the overlay
    - shared schema/example closure
    - residual bridge/router simplification

### P0-2. Human Play Runtime Recovery

Source plan:
- `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`

Goal:
- make the React/FastAPI surface feel like a playable board game, not a replay inspector

Current focus:
- spectator continuity during other players' turns
- strong weather / movement / landing / purchase / rent visibility
- prompt UX that is obvious, blocking only when actually actionable, and readable on first glance
- protect against previously reported regressions

### P0-3. Game Rules Parity

Source plan:
- `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
- `docs/Game-Rules.md`

Goal:
- engine / server / web must reflect the latest rules document

Current focus:
- human prompt semantics
- visual timing for weather / fortune / flips / marks / lap reward
- no UI rendering that implies the wrong rule

### P0-4. String Resource / Encoding Stabilization

Source plans:
- `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
- `PLAN/[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`

Goal:
- remove fragile inline user-facing strings from active UI surfaces
- prevent mojibake regressions
- prepare clean KO/EN switching

Current focus:
- keep locale resources outside components
- reduce remaining `uiText.ts` compatibility-bridge ownership
- move selector-visible wording toward locale-aware boundaries
- keep canonical prompt/public-context field usage aligned with locale-safe boundaries

## P1. Stabilization

### P1-1. Human E2E Hardening
- `1 human + 3 AI` full-path confidence
- browser smoke and parity flows
- timeout/fallback visibility

### P1-2. Parameter-Driven Decoupling Follow-up
Source plan:
- `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`

Goal:
- prevent tile/rule/character/trick parameter changes from breaking web/runtime assumptions

### P1-3. Contract / Selector Cleanup
- reduce selector ownership of locale-specific sentences
- move toward key + params or canonical payload at selector boundaries

## P2. Secondary / Deferred

### P2-1. Broader React architecture/history documents
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`

Status:
- reference-only unless a task explicitly needs them

### P2-2. Older audit / proposal / strategy records

Status:
- supporting context only
- do not use as the main task list

## Always-Read Order

1. `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
3. `docs/Game-Rules.md`
4. `PLAN/[PLAN]_UNIFIED_DECISION_API_DETAILED_EXECUTION.md`
5. `PLAN/[PLAN]_HUMAN_PLAY_RULE_LOG_PARITY_AND_DI.md`
6. `PLAN/[PLAN]_GAME_RULES_ALIGNMENT_AUDIT_AND_FIX_PLAN.md`
7. `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`
8. `PLAN/[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`
9. `PLAN/[PLAN]_PARAMETER_DRIVEN_RUNTIME_DECOUPLING.md`
10. `PLAN/PLAN_STATUS_INDEX.md`

## Current Execution Order

Implement in this order unless a blocker forces a swap:

1. selector/resource locale detachment
2. prompt surface cleanup on top of the locale foundation
3. non-local turn theater continuity
4. rule-parity visual fixes
5. parameter/contract decoupling follow-up

## Current Closed Slices

These are finished enough that they should not be reopened unless regression evidence appears.

1. known prompt types are locked to specialized prompt surfaces
2. `pabal_dice_mode` is now a real human prompt seam
3. payoff continuity survives `turn_end_snapshot`
4. spectator/stage handoff visibility is in browser regression coverage

## Current Carry-Forward Order

This is the practical next-work list after the closed slices above.

1. continue selector-generated locale ownership reduction
2. use regression evidence to close any remaining rule-parity visual gaps
3. harden the external-AI participant path beyond the reference worker

### 2026-04-07 Progress Update (DecisionPort + frontend canonical prompt checkpoint)

- Server/runtime work advanced from “prep” into a live path:
  - runtime human/AI dispatch was split into local decision-client adapters
  - bridge routing was thinned behind a decision-client router
  - engine `DecisionPort` injection is now exercised by the server runtime path
  - engine/server requests are aligned around canonical metadata:
    - `request_type`
    - `player_id`
    - `round_index`
    - `turn_index`
    - `public_context`
    - `fallback_policy`
  - engine `DecisionRequest` creation is now also injectable, which opens the seam for non-default client adapters
- Web prompt consumption also moved closer to the canonical contract:
  - `promptSelectors.ts` now parses only `legal_choices`
  - `PromptOverlay.tsx` now prefers canonical prompt `public_context` keys
  - `selectTurnStage(...)` can derive prompt focus from `legal_choices[].value.tile_index`
- Therefore the next immediate execution order is:
  1. remote-turn payoff continuity and prompt-surface simplification are now closed enough for the current checkpoint
  2. shared prompt artifacts now freeze canonical `legal_choices`
  3. external-AI runtime routing is now parameter-driven and transport-aware:
     - seat descriptors preserve participant intent
     - resolved participant defaults flow into session/runtime state
     - runtime can branch between loopback and http-shaped external-AI transports
     - http transport now has:
       - frozen request/response artifacts
       - canonical legal choices
       - choice-id parsers back into engine-native results
       - retry / backoff / fallback policy
  4. the next immediate execution order is therefore:
     - the reference external worker/service is now mounted against the frozen HTTP contract
     - continue trimming selector-owned phrasing
     - only then widen parameter/profile expansion

### 2026-04-07 Progress Update (external AI worker mount)

- The frozen external-AI contract is now exercised by a real worker service, not only by server-local seams:
  - `apps/server/src/external_ai_app.py` exposes `/health` and `/decide`
  - `apps/server/src/services/external_ai_worker_service.py` selects canonical `choice_id` values from `legal_choices`
  - worker responses now also include matched `choice_payload` metadata for debugging/inspection
  - `tools/run_external_ai_worker.py` is the local runner for dev/test
  - `docs/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md` documents startup, health checks, and session payload wiring
- Regression coverage now includes:
  - worker API contract tests
  - real localhost HTTP round-trip from runtime transport to worker app
- Therefore the practical next-work list becomes:
  1. continue selector-generated locale ownership reduction
  2. keep closing rule-parity visual gaps where replay/live evidence shows drift
  3. harden external-AI auth/retry/worker capability only after the current P0 UI/runtime queue is calmer

### 2026-04-07 Progress Update (selector + effect-visibility + worker hardening pass)

- Web/runtime parity advanced again:
  - selector-side stream formatting moved a little further into locale resources:
    - decision-requested detail
    - decision-resolved detail
    - weather detail
    - marker-flip detail
  - prompt selectors now mark canonical secondary choices explicitly, so prompt surfaces do not have to infer passive/skip state only from raw `choice_id`
  - turn-stage and spectator surfaces now preserve:
    - weather summary
    - lap reward summary
    - mark resolution summary
    - active flip summary
- External-AI runtime hardening also moved forward:
  - participant defaults now include:
    - `contract_version`
    - `expected_worker_id`
    - `auth_token`
    - `auth_header_name`
    - `auth_scheme`
    - `healthcheck_path`
    - `healthcheck_ttl_ms`
    - `required_capabilities`
  - runtime HTTP transport can preflight worker health / contract-version / capability compatibility
  - worker auth / identity validation now applies even when custom sender or custom healthchecker seams are injected
  - frozen external-AI examples now cover:
    - `purchase_tile`
    - `movement`
    - `lap_reward`
    - `mark_target`
    - `active_flip`

### 2026-04-07 Progress Update (external worker identity/auth hardening + mixed-seat regression)

- The external participant seam is now closer to an operational multiplayer boundary:
  - runtime validates `expected_worker_id` on both health and decision responses
  - auth header merge is parameter-driven via:
    - `auth_header_name`
    - `auth_scheme`
    - `auth_token`
  - the worker app now actually reads the configured auth header name instead of only `Authorization`
  - injected/custom sender and healthchecker seams no longer bypass identity validation
- Regression coverage expanded:
  - worker API auth-required coverage

### 2026-04-07 Progress Update (remote-turn worker status continuity)

- Remote-turn continuity improved again around external-worker participation:
  - current-turn stage/spectator models now preserve external-worker status not only from timeout fallback payloads, but also from normal `decision_resolved` payloads
  - stage/spectator surfaces now keep a dedicated participant-status block visible across consecutive worker-success and local-fallback turns
  - the runtime seam now records attempt counts so repeated worker retries remain inspectable in canonical `public_context`
- Practical meaning:
  - remote turns read more like multiplayer participant turns than opaque replay rows
  - mixed-seat playtests can now verify worker success and fallback continuity across adjacent turns without relying only on event-feed details
  - runtime fallback on worker-identity mismatch
  - runtime validation for custom healthchecker identity mismatch
  - mixed-seat browser runtime with `human_http + local_ai + external_ai` descriptors

### 2026-04-07 Progress Update (selector locale ownership + timeout visibility)

- Selector-side text ownership moved another step toward locale resources:
  - actor-prefixed stream details now go through locale helpers instead of selector-local string joins
  - timeout fallback detail formatting is now locale-owned too
- Current-turn visibility also improved:
  - `decision_requested`
  - `decision_resolved`
  - `decision_timeout_fallback`
  now persist into the turn-stage/spectator flow for the current turn instead of being effectively overlay-only context
- Regression coverage expanded:
  - selector unit coverage for timeout fallback detail rendering
  - selector unit coverage for timeout fallback persistence in turn stage
  - browser E2E coverage for remote timeout fallback visibility

### 2026-04-07 Progress Update (default-text bridge reduction + external worker ops follow-up)

- Web:
  - label/selector defaults now read from `i18n/defaultText.ts` instead of importing the older `uiText.ts` bridge directly
  - `uiText.ts` remains as a compatibility shim rather than the primary default-text source
  - prompt head chrome now always uses the compact pill set to keep the surface less inspector-like
- Server:
  - external HTTP transport now records worker diagnostics into canonical public context:
    - `external_ai_worker_id`
    - `external_ai_failure_code`
    - `external_ai_failure_detail`
    - `external_ai_fallback_mode`
  - failure classification now distinguishes timeout vs known runtime seam codes instead of relying only on raw exception text
  - reference worker capability metadata now includes:
    - `failure_code_response`
    - `worker_identity`
- Ops/docs:
  - added a production-shaped external worker session payload example
- Therefore the next practical order becomes:
  1. continue trimming remaining selector-owned phrasing
  2. keep using browser/runtime evidence to close any leftover rule-parity visuals
  3. only after that, widen external-AI auth / richer worker implementation work

### 2026-04-07 Progress Update (default-text shim closure)

- `uiText.ts` is now effectively a compatibility export surface, not the primary regression target:
  - the primary default-text regression coverage now lives under `apps/web/src/i18n/defaultText.spec.ts`
  - `apps/web/src/domain/text/uiText.spec.ts` now only checks that the shim re-exports the default catalogs
- selector text ownership moved one step further toward locale resources:
  - `decision_ack` detail is now locale-owned
  - generic runtime `error` detail is now locale-owned
- Therefore the next practical order narrows again:
  1. keep removing any remaining selector-local summary/detail joins
  2. finish prompt surface simplification only where it still leaks meta-heavy framing
  3. keep worker/runtime hardening focused on true operational gaps, not text-layer cleanup

### 2026-04-07 Progress Update (external worker status surfacing)

- timeout fallback rendering now exposes external worker runtime context instead of only a generic summary:
  - `external_ai_worker_id`
  - `external_ai_failure_code`
  - `external_ai_fallback_mode`
- runtime transport also now records a normalized `external_ai_resolution_status` into canonical public context so downstream consumers can distinguish:
  - resolved by worker
  - worker failed
  - resolved by local fallback
- generic prompt fallback surfaces now collapse secondary choices under a lighter disclosure instead of giving them equal visual weight
- Therefore the next practical order narrows further:
  1. finish the remaining selector-local joins only where they still block locale ownership
  2. keep prompt simplification focused on leftover generic/specialized duplication rather than headline chrome
  3. keep pushing external worker hardening toward real operational concerns:
     - auth
     - health gating
     - stronger worker behavior

### 2026-04-07 Progress Update (selector parsing + prompt section dedup)

- selector-side prompt parsing is now more explicitly normalized:
  - choice title extraction
  - choice description extraction
  - secondary-choice inference
  all live behind smaller helper functions instead of one large inline branch
- specialized prompt surfaces now share a lighter common section wrapper for repeated summary-pill + grid layouts
- Therefore the next practical order narrows again:
  1. finish only the remaining selector-local summary/detail joins that still leak phrase ownership
  2. keep simplifying prompt surfaces where specialized layouts still duplicate each other materially
  3. leave deeper worker/runtime work for slices that actually need transport/ops changes

### 2026-04-07 Progress Update (worker status surfaced as participant UI)

- external worker state is no longer only embedded inside fallback text:
  - turn stage now has a dedicated participant-status card
  - spectator panel now has a dedicated participant-status card
  - the turn-stage model keeps normalized worker fields directly
- runtime hardening also moved one step forward:
  - worker health/response payloads now validate `supported_request_types` when present
  - public context now records `external_ai_attempt_count`
- browser parity now explicitly covers a consecutive mixed-seat scenario where:
  1. one external-AI turn resolves by worker
  2. the next external-AI turn falls back locally
- Therefore the next practical order narrows to:
  1. visual drift closure only where remote-turn sequencing still feels less than scene-grade
  2. stronger worker/runtime ops hardening:
     - auth
     - health gating
     - richer deployment behavior
  3. higher-quality external worker behavior beyond the current heuristic baseline

## 2026-04-05 Concrete Next Steps

1. Keep `apps/web/src/i18n/` as the source of truth and remove new direct ownership from:
   - selectors
   - runtime-facing prompt helpers
   - theater/stage summary helpers
2. Continue prompt cleanup with the locale resource model:
   - movement
   - trick
   - purchase
   - mark
   - lap reward
3. Preserve non-local turn continuity so the match reads as:
   - actor start
   - movement
   - landing
   - purchase/rent/fortune
   - turn end
4. Only after the above, continue selector/key decoupling and parameter-driven follow-up.

### 2026-04-05 Progress Update

- `streamSelectors.ts` now accepts locale-aware text resources instead of forcing runtime rendering through the Korean compatibility bridge.
- `App.tsx` now passes current locale resources into:
  - timeline
  - theater
  - alert
  - situation
  - turn-stage selectors
- Therefore the next immediate implementation order is:
  1. keep trimming selector-owned phrase composition
  2. continue prompt/theater human-play cleanup
  3. only then return to lower-priority decoupling follow-up

### 2026-04-06 Progress Update

- Remote-turn board continuity now preserves and renders intermediate move-path tiles, not only move origin/destination.
- As a result, the next immediate P0-2 slice should stay focused on:
  1. theatrical fortune / purchase / rent staging after movement completes
  2. stronger pawn/path animation on top of the new path-step groundwork
  3. continued local prompt simplification on the locale-safe foundation

### 2026-04-06 Progress Update (current checkpoint)

- The board now also renders a transient ghost-pawn travel overlay between move start and move end.
- Prompt surface wording is now further detached from component ownership:
  - collapsed prompt chip text
  - prompt footer request-meta text
  - purchase prompt description text
  now come from locale resources.
- `DecisionGateway` now also centralizes repeated lifecycle publish paths for:
  - `decision_requested`
  - `decision_resolved`
  - `decision_timeout_fallback`
- Therefore the next immediate execution order is:
  1. continue prompt-surface cleanup until remaining live prompts feel game-native instead of inspector-like
  2. keep strengthening non-local turn scene payoff for fortune / purchase / rent
  3. continue reducing human/AI branch-local decision drift before later `DecisionPort` migration

### 2026-04-06 Progress Update (remaining generic prompt split)

- The remaining previously-generic prompt families:
  - `runaway_step_choice`
  - `coin_placement`
  - `doctrine_relief`
  - `geo_bonus`
  now render on dedicated emphasized live-choice surfaces instead of the generic fallback grid.
- Backend specialty coverage now also explicitly guards:
  - `doctrine_relief`
  - `burden_exchange`
- Therefore the next immediate execution order is:
  1. finish scene-grade payoff for fortune / purchase / rent so outcomes feel like events instead of feed entries
  2. continue trimming any still-rare generic prompt fallback surfaces
  3. after the above, move P0-1 from seam-coverage work toward typed provider cleanup / `DecisionPort` prep

### 2026-04-06 Progress Update (specialty coverage checkpoint)

- Specialty decision coverage now explicitly includes:
  - `runaway_step_choice`
  - `coin_placement`
  - `geo_bonus`
  in addition to the already-covered specialty paths.
- Scene payoff cards also now use a shared pulse treatment so purchase / rent / fortune outcomes stand out more clearly during live turns.
- Therefore the next immediate execution order is:
  1. continue true human-play UX work:
     - stronger fortune reveal staging
     - richer purchase/rent event transitions
     - remaining prompt-surface simplification
  2. keep reducing any residual generic fallback prompt usage
  3. only after that, return to typed provider cleanup and later `DecisionPort` migration

### 2026-04-06 Progress Update (locale persistence checkpoint)

- Locale restore is now explicitly guarded:
  - both `ko` and `en` survive reload
  - invalid stored values fall back to the default locale
  - locale buttons have stable ids and browser coverage
- Therefore the next immediate execution order remains:
  1. continue prompt-surface cleanup until remaining live prompts feel game-native instead of inspector-like
  2. keep strengthening non-local turn scene payoff for fortune / purchase / rent and turn-to-turn handoff
  3. continue reducing human/AI branch-local decision drift before later `DecisionPort` migration

### 2026-04-06 Progress Update (spectator journey + mark drift)

- Remote turns now also expose a dedicated spectator journey strip, not only payoff and spotlight cards.
- Prompt display order now keeps passive `none`/skip-style entries behind actionable options where applicable.
- AI-side canonical request coverage now explicitly includes `mark_target`.
- Therefore the next immediate execution order is:
  1. continue trimming prompt surfaces that still feel inspector-like
  2. continue scene-grade continuity for fortune / purchase / rent / turn handoff
  3. extend canonical decision coverage to remaining specialty methods before full `DecisionPort` migration

### 2026-04-06 Progress Update (spectator result + active flip)

- Prompt request-meta moved into the prompt head, reducing footer inspector feel.
- Remote turns now keep a dedicated spectator result card for the latest payoff beat.
- AI-side canonical request coverage now also explicitly includes `active_flip`.
- Therefore the next immediate execution order is:
  1. finish the remaining specialty prompt simplification slices
  2. continue scene-grade continuity for weather / fortune / purchase / rent handoff
  3. extend canonical decision coverage to the remaining specialty methods before full `DecisionPort` migration

### 2026-04-06 Progress Update (weather spotlight + specific reward)

- Remote-turn weather is now also promoted into the spectator spotlight strip.
- Remote-turn journey continuity now separates:
  - purchase
  - rent
  - fortune
  into their own beats when present.
- Specialty prompt layouts now also explicitly cover:
  - `active_flip`
  - `burden_exchange`
  - `specific_trick_reward`
- AI-side canonical request coverage now also explicitly includes `specific_trick_reward`.
- Therefore the next immediate execution order is:
  1. keep trimming the last remaining generic/inspector-feeling prompt states
  2. keep strengthening scene-grade continuity for fortune reveal and purchase/rent payoff transitions
  3. extend canonical decision coverage to the remaining specialty methods before full `DecisionPort` migration

### 2026-04-06 Progress Update (pabal seam fixed)

- `pabal_dice_mode` is now a real human prompt path, not an AI-only specialty branch.
- Prompt choice parsing now also recognizes `value.description`, reducing future specialty prompt drift.
- Therefore the next immediate execution order is:
  1. continue scene-grade continuity for fortune reveal / purchase / rent / turn handoff
  2. keep trimming the last remaining inspector-feeling prompt surfaces
  3. move P0-1 from “missing specialty seams” to typed-provider / `DecisionPort` cleanup
### 2026-04-06 Progress Update (prompt HUD + explicit payoff labels)

- Prompt overlays now use a compact HUD-style head instead of a debug-like request sentence.
- Turn-stage and spectator payoff cards now prefer explicit event labels for:
  - landing resolved
  - tile purchased
  - rent paid
  - fortune drawn
  - fortune resolved
- Therefore the next immediate execution order is:
  1. continue scene-grade continuity for true turn handoff and payoff animation
  2. keep trimming any still-generic prompt surface that does not yet feel game-native
  3. after the above, keep collapsing provider drift toward the typed `DecisionPort` boundary

### 2026-04-06 Progress Update (turn handoff surfaced)

- Turn-end summaries are now promoted into dedicated handoff cards in both:
  - spectator panel
  - turn stage
- Browser parity now explicitly checks that remote-turn handoff remains visible.
- Therefore the next immediate execution order is:
  1. continue payoff animation and scene-beat polish for fortune / purchase / rent
  2. trim any remaining generic prompt presentation that still feels like a fallback list
  3. continue reducing provider-local drift before typed `DecisionPort` cleanup

### 2026-04-06 Progress Update (payoff survives turn_end)

- The public action result card now follows the latest payoff beat from the same turn, not merely the most recent event.
- This means purchase / rent / fortune payoff remains visible after `turn_end_snapshot`.
- Therefore the next immediate execution order is:
  1. continue scene-beat polish for fortune reveal and payoff transitions
  2. finish trimming the remaining generic prompt surfaces
  3. keep shrinking provider-local drift before typed `DecisionPort` cleanup

### 2026-04-06 Progress Update (specialized prompt coverage locked)

- Known prompt types are now explicitly locked to specialized prompt surfaces.
- The generic prompt grid now represents only unknown / future request types.
- Build, focused Vitest coverage, and human-play browser regression all passed after the lock was added.
- Therefore the next immediate execution order is:
  1. continue scene-beat polish for fortune reveal and payoff transitions
  2. keep simplifying the specialized prompt layouts themselves
  3. keep shrinking provider-local drift before typed `DecisionPort` cleanup

### 2026-04-06 Documentation Alignment Checkpoint

- Closed and carry-forward work were reclassified so the current board is easier to read at a glance.
- Use the following interpretation from now on:
  1. closed:
     - prompt specialization lock
     - `pabal_dice_mode` seam repair
     - payoff continuity across turn-end
  2. still active:
     - fortune / purchase / rent scene payoff
     - specialized prompt simplification
     - provider-local drift reduction before typed `DecisionPort` cleanup
