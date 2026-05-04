# [ACTIVE] UI/UX Future Work Canonical

Status: ACTIVE_CANONICAL  
Updated: 2026-05-04
Owner: Codex

## Purpose

This is the only frontend UI/UX execution document that should be used going forward.

It merges and replaces the scattered open work that used to live across:

- `docs/archive/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`
- `docs/archive/frontend/[PLAN]_BOARD_COORDINATE_SYSTEM_AND_HUD_LAYOUT_STABILIZATION.md`
- `docs/archive/frontend/[PLAN]_LIVE_PLAY_STATE_AND_DECISION_RECOVERY.md`
- `docs/archive/frontend/[PLAN]_PAWN_MOVEMENT_AND_EVENT_ANIMATION.md`
- `docs/archive/frontend/[REPORT]_UI_UX_VALIDATION_AND_COMMERCIAL_BENCHMARK_2026-04-15.md`

Older proposal and report docs now live under `docs/archive/frontend/` and remain only as archived references.

## How To Use This Doc

Use this document for:

- understanding what work was executed in the latest UI/UX stabilization pass
- checking the completion baseline before adding new frontend UI work
- avoiding reopening already-merged execution docs

Do not reopen older UI/UX docs as execution sources unless this document explicitly tells you to.

---

## Current State

The current frontend is no longer in “start from scratch” territory.

What is already good enough to keep:

- board-first composition is in place
- the top player strip is compact enough for desktop play
- the prompt shell is vertically tighter than before
- hand tray and prompt overlap are much better controlled
- current actor/local player emphasis exists

What was completed in this pass:

1. semantic color hierarchy across HUD, prompt, and player identity
2. remaining layout ownership cleanup around board-owned overlay layout
3. live-play correctness hardening for visible seat/player rendering during runtime startup
4. event/result feed semantic styling and motion polish
5. browser-based validation recovery with real 1920x1080 play verification through live prompts
6. board landmark strengthening for tile-type readability
7. choice-card hierarchy redesign with summary/detail separation
8. result spotlight fallback so recent purchase/effect beats remain visible across prompt transitions

Open scheduled items:

- final 2H+2AI and 4-human playtest evidence for effect cause visibility across `잔꾀`, `운수`, `날씨`, character passives, and AI-triggered follow-up prompts.
- active weather should remain visible as round context if the final playtest still shows weather/result attribution fading too quickly.

---

## Rules

1. Do not restart the UI from zero.
2. Keep the board as the visual hero.
3. Prefer selector/contract fixes before CSS if the state shown is wrong.
4. Reduce chrome before increasing panel size.
5. Use semantic color roles, not arbitrary color variation.

---

## Execution Backlog

### P0. Effect Cause Visibility During Live Play

Status: BASELINE IMPLEMENTED AND AUTOMATED GATE PASSED (2026-05-04), FINAL MANUAL PLAYTEST PENDING

Goal:
- make every rule-driven state mutation understandable at the moment it happens, especially when the next prompt appears immediately

Evidence:
- In 2-human + 2-AI session `sess_CrAt2zEMf9W79JjFauDvHDf7`, P2's `거대한 산불` was readable: the source player, card name, effect text, hand removal, and shard gain were visible.
- P1's earlier `과속` state update was correct, but the visible attribution was weak compared with `거대한 산불`.
- P4 AI's `아주 큰 화목 난로` led into a P1 `짐 카드 교환` prompt before P1 had a durable, readable source/effect explanation.
- Round 2 weather removed P1 burden cards and dropped cash from 18 to 10, but the next `잔꾀 쓰기` prompt did not carry a clear weather/result explanation.

Implement:
- keep a recent effect/result panel visible across the next blocking prompt
- include source player, effect family, card/weather name, and resource delta in follow-up prompts created by that effect
- ensure AI-triggered effects use the same visual treatment as human-triggered effects
- keep current weather visible as active round context, not only as a transient stream event

Implemented baseline:
- backend-provided `effect_context.source_player_id`, `source_family`, `source_name`, and `resource_delta` now survive selector parsing, `App.tsx` prompt mapping, and `PromptOverlay` rendering.
- prompt overlay renders source chips for source player, effect family, and card/weather name, plus resource delta chips when a non-zero known delta exists.
- AI-triggered and human-triggered follow-up prompts use the same effect context route when the backend provides the same fields.

Automated evidence:
- `apps/server/tests/test_view_state_prompt_selector.py::ViewStatePromptSelectorTests::test_build_prompt_view_state_projects_effect_context` and `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_effect_context_covers_remaining_effect_prompt_boundaries` passed on 2026-05-04.
- `src/features/prompt/promptEffectContextDisplay.spec.ts` and `src/domain/selectors/promptSelectors.spec.ts` passed on 2026-05-04.
- `npm --prefix apps/web run e2e:human-runtime` passed all 18 checks on 2026-05-04, including fortune cash loss, innkeeper lap bonus, Manshin mark, Baksu burden transfer, matchmaker purchase, and mixed participant continuity cases.
- Detailed evidence lives in `docs/current/engineering/[EVIDENCE]_RUNTIME_CONTRACT_EXTERNAL_CHECKS_2026-05-04.md`.

Definition of done:
- a player can explain why a cash, shard, hand-count, burden, movement, or purchase prompt changed without reading debug logs
- `잔꾀`, `운수`, `날씨`, and character passive bonuses all leave a visible cause-and-effect artifact during 2H+2AI and 4-human playtests

### P0. Semantic Color Refactor

Status: DONE (2026-04-15)

Goal:
- move from one navy-heavy UI to a commercial-style semantic palette while keeping the same dark overall mood

Implement:
- add semantic CSS tokens in `apps/web/src/styles.css`
- split visual roles into:
  - board/base surfaces
  - decision/prompt surfaces
  - economy success/danger accents
  - stable player identity accents

Minimum token set:
- `--ui-surface-base`
- `--ui-surface-raised`
- `--ui-surface-board`
- `--ui-accent-decision`
- `--ui-accent-success`
- `--ui-accent-danger`
- `--ui-player-1`
- `--ui-player-2`
- `--ui-player-3`
- `--ui-player-4`

Definition of done:
- prompt shell no longer reads like the same surface as the neutral HUD
- player strip reads by seat color faster than by text
- gain/loss/risk cues are understandable without reading every chip

### P0. Prompt And Choice Hierarchy

Status: DONE (2026-04-15)

Goal:
- make the prompt the warm, obvious action surface without making it larger again

Implement:
- keep the top timer bar as the primary prompt header signal
- restyle prompt pills by semantic role
- make the primary action button visually distinct from passive controls
- keep effect text readable by reducing supporting chrome first

Targets:
- `apps/web/src/features/prompt/PromptOverlay.tsx`
- `apps/web/src/styles.css`

Definition of done:
- the active decision area is visually dominant over neutral HUD panels
- prompt chips have at least three readable semantic groups: neutral, active, gain/loss

### P0. Player Strip Identity Upgrade

Status: DONE (2026-04-15)

Goal:
- make player recognition color-led and peripheral-vision friendly

Implement:
- strengthen per-player accent rail or header tint
- keep `나`, seat type, and marker ownership small but clear
- let active/local states lean on player color before extra labels

Targets:
- `apps/web/src/App.tsx`
- `apps/web/src/styles.css`

Definition of done:
- each seat is recognizable in under a second
- the currently relevant player does not require reading every card

### P1. Hand Tray Density Cleanup

Status: DONE (2026-04-15)

Goal:
- fit long trick descriptions more reliably without growing the tray

Implement:
- remove one unnecessary chrome layer around the tray
- keep card text top-aligned
- shrink title/support copy before shrinking effect copy
- tune line-height and padding before changing tray height

Targets:
- `apps/web/src/App.tsx`
- `apps/web/src/features/prompt/PromptOverlay.tsx`
- `apps/web/src/styles.css`

Definition of done:
- no common trick description is clipped at 1920x1080
- tray remains within the board-safe bottom band

### P1. Layout Ownership Cleanup

Status: DONE (2026-04-15)

Goal:
- finish the remaining board/HUD anchoring cleanup so layout rules do not stay split across viewport guesses and board-owned values

Implement:
- move remaining prompt/tray/event-lane compensations out of `App.tsx`
- consolidate safe-band ownership around board layout metadata

Targets:
- `apps/web/src/App.tsx`
- board layout related styles and measurement hooks

Definition of done:
- prompt anchoring, public event lane placement, and tray bottom alignment are not controlled by scattered viewport magic numbers

### P1. Live-Play Correctness And Selector Hardening

Status: DONE (2026-04-15)

Goal:
- ensure UI improvements sit on truthful runtime state

Implement:
- finish legal purchase candidate handling
- preserve correct arrival / purchase / follow-up order
- keep spend/result timing truthful
- ensure stable trick card identity through all relevant prompt flows
- continue moving selector truth to backend-derived models where appropriate

Primary areas:
- `apps/server/src/services/decision_gateway.py`
- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/domain/selectors/promptSelectors.ts`
- `apps/web/src/features/prompt/PromptOverlay.tsx`

Definition of done:
- no duplicate-card ambiguity
- no invalid purchase prompts
- no visible “money changed before result resolved” confusion

### P2. Event Feed And Outcome Semantics

Status: DONE (2026-04-15)

Goal:
- make the turn narrative easier to scan without adding more clutter

Implement:
- add or refine a concise event/result feed
- color-code gain/loss/risk outcomes
- reserve large type for the dramatic beat, not for constant status

Definition of done:
- a spectator can understand the last important turn beat from one glance

### P2. Pawn Movement And Event Animation

Status: DONE (2026-04-15)

Goal:
- add motion polish only after layout and correctness work are stable

Implement:
- refine pawn path travel
- align reveal/event timing with turn beats
- keep animations readable rather than flashy

Source material:
- `docs/archive/frontend/[PLAN]_PAWN_MOVEMENT_AND_EVENT_ANIMATION.md` is now reference-only

Definition of done:
- movement and outcome reveals add clarity instead of delaying decision readability

### P2. Browser Visual Verification Recovery

Status: DONE (2026-04-15)

Goal:
- restore true browser-based UI validation

Current blocker:
- local browser launch and MCP browser session stability are preventing reliable visual E2E verification

Implement:
- recover a stable browser runtime path
- rerun 1920x1080 visual checks through 2-3 turns
- verify prompt, tray, player strip, and board event readability in actual play

Definition of done:
- the latest UI pass is verified in a real browser, not only by CSS/code inspection

---

## Verification Baseline

Latest completion pass included:

1. `npm run test` in `apps/web`
2. `npm run build` in `apps/web`
3. real Playwright MCP verification at `1920x1080`
4. live interaction through multiple prompt transitions
5. post-fix browser console check with `0` errors

---

## Reopened Live-Play UX Findings

Date: 2026-05-01  
Source: Redis-backed 2-human + 2-AI browser playtest

### P0. Effect Attribution Must Be Screen-Readable

Status: OPEN

Problem:
- The game can apply a rule correctly while the player cannot see why the state changed.
- This is especially risky for `운수`, `잔꾀`, `날씨`, and passive character bonuses because their effects can be indirect or short-lived.

Observed:
- `잔꾀` hand mutation is mostly readable: using `무료 증정` immediately removed it from the tray and changed visible hand count from 5 to 4.
- shard gain from `거대한 산불` was reflected immediately in previous 2H+2AI evidence.
- `운수` money loss was correct in engine/replay, but the visible explanation can disappear too quickly; a later lower cash total is not enough.
- `객주` reward enhancement is applied after lap reward in backend state, but the visible reward event does not clearly break out the passive bonus.
- 2026-05-01 2H+2AI continuation found a stale tray rendering: Redis/current player panel showed P1 `Trick0` and empty `trick_hand`, but the bottom `Trick hand` tray still showed the consumed `뭔칙휜` card.
- The same continuation showed repeated P1 movement prompts after a reroll-style trick path. Even if some prompts are stale and rejected by the backend, the screen can still make the player believe the action is unresolved or repeating.

Required UX behavior:
- every money/shard/coin/position delta caused by `운수` must produce a persistent enough reveal/feed line with card name and delta
- every `잔꾀` use must show card name, effect summary, resource/hand delta, and immediate tray removal
- every weather effect that changes resource or marker behavior must remain named in the current round context while the player acts
- every passive character bonus, starting with `객주`, must show either a separate bonus line or a combined breakdown such as `기본 보상 + 객주 보너스`
- hand/tray rendering must derive from the latest visible player state and clear consumed cards after prompt or stream replay
- superseded or already-resolved prompts must not remain visually actionable after a newer prompt for the same player/turn/type exists

Definition of done:
- a player can answer "what changed, why, and by how much?" from the screen alone after each public effect
- Playwright/browser snapshots assert both final state and cause text for `잔꾀`, `운수`, `날씨`, and `객주`
- no pending prompt from an already-consumed trick path can later reappear as a confusing hidden-card prompt

---

## Closed And Superseded Docs

These docs should no longer be used as execution sources:

- `docs/archive/frontend/[ACTIVE]_UI_UX_PRIORITY_ONE_PAGE.md`
- `docs/archive/frontend/[PLAN]_BOARD_COORDINATE_SYSTEM_AND_HUD_LAYOUT_STABILIZATION.md`
- `docs/archive/frontend/[PLAN]_LIVE_PLAY_STATE_AND_DECISION_RECOVERY.md`
- `docs/archive/frontend/[PLAN]_PAWN_MOVEMENT_AND_EVENT_ANIMATION.md`
- `docs/archive/frontend/[REPORT]_UI_UX_VALIDATION_AND_COMMERCIAL_BENCHMARK_2026-04-15.md`

These docs remain historical/reference only:

- `docs/archive/frontend/[PROPOSAL]_UI_UX_COMMERCIAL_REDESIGN.md`
- `docs/archive/frontend/[PROPOSAL]_UI_UX_DETAILED_SPEC.md`
- `docs/archive/frontend/[PROPOSAL]_UI_UX_ISSUE_FIX_PLAN.md`
- `docs/archive/frontend/[PROPOSAL]_UI_UX_REDESIGN_FROM_SCRATCH.md`
- `docs/archive/frontend/[REPORT]_LIVE_PLAY_UX_FINDINGS_2026-04-07.md`

---

## Success Criteria

This canonical document can be considered complete when:

1. color hierarchy is semantic and commercially readable
2. prompt, tray, and player strip stay readable at 1920x1080
3. remaining layout ownership drift is removed
4. live-play prompt correctness issues are closed
5. browser-based visual verification is running again
