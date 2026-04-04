# [WORKLOG] Implementation Journal

Status: ACTIVE  
Updated: 2026-04-04

## Rules

- Record every task summary regardless of size (small/large).
- For complex logic changes, write/update plan docs first, then implement.

## 2026-04-04

### Entry 001

- Scope: policy guardrail hard-fix and mandatory reading stabilization.
- Done:
  - Added CI gate workflow for policy checks.
  - Added `tools/plan_policy_gate.py`.
  - Linked mandatory docs in PLAN index and backend README.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Start P0-1: Unified Decision API contract/order audit and runtime alignment.

### Entry 002

- Scope: mandatory principle update + P0-1 kickoff implementation.
- Done:
  - Added mandatory rules:
    - small/large work must be summarized into work journal
    - complex logic changes must start from plan doc
  - Rewrote mandatory/priority docs in UTF-8 to avoid encoding ambiguity.
  - Started P0-1 implementation in server runtime:
    - emit `decision_requested` on prompt registration
    - emit `decision_resolved` on accepted/timeout-fallback/parser-fallback
  - Added runtime unit-test assertions for decision request/resolve ordering.
- Next:
  - Continue P0-1 contract parity audit for remaining decision lanes.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (6/6).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventToneCatalog.spec.ts` passed (12/12).

### Entry 003

- Scope: P0-1 decision-lane parity expansion (timeout lane + selector visibility).
- Done:
  - Added `decision_resolved` emission before `decision_timeout_fallback` in websocket timeout lane.
  - Expanded stream API test to assert timeout resolution ordering:
    - `decision_resolved` appears before `decision_timeout_fallback`.
  - Rewrote web event label catalog/spec in UTF-8 and added decision event labels.
  - Added selector test coverage for `decision_requested` / `decision_resolved` timeline details.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py -q` passed (`6 passed, 10 skipped`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/eventToneCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`16 passed`).
- Next:
  - Continue P0-1 with remaining decision submit/ack ordering audit for non-timeout branches.

### Entry 004

- Scope: P0-1 deterministic ordering hardening (bridge timeout path).
- Done:
  - Added runtime bridge timeout test:
    - `decision_requested` -> `decision_resolved` -> `decision_timeout_fallback` ordering assertion.
  - Synced server timeout lane to emit `decision_resolved` before timeout fallback.
  - Stabilized web decision-event label/spec coverage.
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`7 passed`).
  - `python -m pytest apps/server/tests/test_stream_api.py -q` passed (`10 skipped`, no failures).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/eventToneCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`16 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-1 non-timeout branch audit in mixed runtime/reconnect conditions.

### Entry 005

- Scope: P0-1 validation planning under local dependency constraints.
- Done:
  - Updated decision API detailed plan with explicit local validation note.
  - Documented FastAPI-gated skip reality and CI-first verification path for non-timeout stream branch.
- Next:
  - Implement/verify non-timeout branch ordering fixture in FastAPI-enabled matrix.

### Entry 006

- Scope: P0-1 non-timeout stream branch CI fixture.
- Done:
  - Added stream API test for normal accepted decision path:
    - seat-authenticated decision submission
    - `decision_ack` accepted verification
  - This fixture is FastAPI-gated and will run in dependency-enabled CI.
- Validation:
  - `python -m pytest apps/server/tests/test_stream_api.py -q` (no failures, FastAPI-gated skips in current local env).

### Entry 007

- Scope: P0-1 decision resolution de-duplication and parser-fallback correctness.
- Done:
  - Fixed runtime bridge ordering bug:
    - accepted `decision_resolved` is now emitted only after parser success.
    - parser failure path emits a single `decision_resolved` with `resolution=parser_error_fallback`.
  - Expanded runtime tests:
    - accepted path asserts exactly one `decision_resolved`.
    - timeout path asserts exactly one `decision_resolved`.
    - parser-error path asserts exactly one `decision_resolved` and fallback return.
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`15 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - P0-1 reconnect/retry mixed-lane audit for non-timeout accepted branch.

### Entry 008

- Scope: P0-1 retry branch determinism (non-timeout).
- Done:
  - Added stream API test fixture for duplicate decision submission on same `request_id`.
  - Expected behavior fixed by test contract:
    - first submit -> `decision_ack: accepted`
    - second submit(retry) -> `decision_ack: stale (already_resolved)`
- Validation:
  - `python -m pytest apps/server/tests/test_stream_api.py -q` (FastAPI-gated skips in current local env, no failures).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
- Next:
  - Extend reconnect/resume scenario to include decision-event replay consistency.

### Entry 009

- Scope: P0-1 reconnect/resume ordering fixture.
- Done:
  - Added stream replay contract test for decision/domain ordering:
    - `decision_requested -> decision_resolved -> player_move` must remain ordered after resume replay.
- Validation:
  - `python -m pytest apps/server/tests/test_stream_api.py -q` (FastAPI-gated skips in current local env, no failures).
- Next:
  - Finalize P0-1 by wiring CI-visible coverage status and preparing P0-2 entry.

### Entry 010

- Scope: P0-1 CI visibility hardening.
- Done:
  - Added dedicated CI workflow:
    - `.github/workflows/backend-decision-contract-tests.yml`
  - CI now runs:
    - `apps/server/tests/test_runtime_service.py`
    - `apps/server/tests/test_stream_api.py`
  - This closes the local FastAPI-gated skip blind spot by validating in CI environment.
- Validation:
  - Workflow file created and tracked.
- Next:
  - Start P0-2 lane separation implementation (core/prompt/system) in web projection path.

### Entry 011

- Scope: P0-2 lane separation kickoff in turn theater.
- Done:
  - Added theater lane classification in selector path:
    - `core` / `prompt` / `system`
  - Reflected lane in theater item model + rendering.
  - Updated incident card UI with lane badge and lane-specific visual styling.
  - Added selector assertions for lane classification.
- Validation:
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`15 passed`).
- Next:
  - Continue P0-2 by splitting timeline/feed render blocks by lane priority and visibility policy.

### Entry 012

- Scope: P0-2 lane-aware theater rendering.
- Done:
  - Updated theater component to render lane groups:
    - 핵심 진행
    - 선택/응답
    - 시스템
  - Added lane badge and lane-specific visual styling.
  - Preserved tone badges and recent-event emphasis.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/labels/eventLabelCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`15 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 visibility policy: promote other-player core actions to always-visible top block.

### Entry 013

- Scope: P0-2 lane contract test expansion.
- Done:
  - Added selector test to ensure:
    - `decision_requested` and `decision_resolved` are classified as `prompt` lane in theater feed.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`13 passed`).
- Next:
  - Continue P0-2 visibility policy and actor-priority rendering for non-human core actions.

### Entry 014

- Scope: P0-2 theater visibility policy (prompt flood resilience).
- Done:
  - Added lane-aware quota policy in `selectTheaterFeed`:
    - core/prompt/system caps with fallback fill.
  - Ensured feed is still filled to requested limit while preserving core visibility.
  - Added test for prompt-heavy traffic:
    - core event remains visible.
  - Updated theater UI to grouped lane rendering and badges.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`14 passed`).
  - `npm run build` passed (`apps/web`).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 by adding actor-focus priority strategy (non-human core actions + human prompt clarity).

### Entry 015

- Scope: P0-2 actor-focus priority strategy.
- Done:
  - Added `focusPlayerId` binding from app context to theater component.
  - Prioritized non-focus(core) actor events before focus actor events in core lane.
  - Preserved lane grouping and tone/lane badges.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`17 passed`).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 with turn-theater visibility tuning for passive prompts vs actionable prompts.

### Entry 016

- Scope: P0-2 prompt visibility tuning in theater.
- Done:
  - Added prompt-lane priority ordering:
    - `decision_resolved` > `decision_timeout_fallback` > `decision_ack` > `decision_requested` > `prompt`
  - Applied focus actor context so local actionable prompt context is surfaced earlier in prompt lane.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`17 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 by connecting lane visibility policy to match-level collapsible controls (operator UX).

### Entry 017

- Scope: P0-2 operator UX controls for lane visibility.
- Done:
  - Added per-lane collapse controls in turn theater:
    - 핵심 진행 / 선택응답 / 시스템 각각 접기/펼치기
  - Added lane header and toggle styling.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`17 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 with passive/non-actionable prompt demotion tuning in theater + timeline.

### Entry 018

- Scope: P0-1 closure reinforcement (mixed-path runtime contracts + human-play regression safety).
- Done:
  - Added ordered sequence contract fixtures:
    - `packages/runtime-contracts/ws/examples/sequence.decision.accepted_then_domain.json`
    - `packages/runtime-contracts/ws/examples/sequence.decision.timeout_then_domain.json`
  - Added runtime contract test coverage for ordered decision/domain sequences:
    - `apps/server/tests/test_runtime_contract_examples.py`
  - Expanded backend contract CI workflow to include runtime contract fixture tests.
  - Added selector regression coverage for mixed human-play decision flow:
    - decision lane remains visible
    - core progression (`dice_roll`, `player_move`, `landing_resolved`) remains visible
    - raw prompt is system lane noise, not blocking core.
  - Updated plan docs with latest P0-1 status snapshot.
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_contract_examples.py -q` passed (`2 passed`).
  - `python -m pytest apps/server/tests/test_runtime_service.py -q` passed (`8 passed`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`19 passed`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Push and verify CI result of `backend-decision-contract-tests`.
  - Continue P0-2 live screen UX parity corrections.

### Entry 019

- Scope: P0-2 live-screen UX parity pass (board readability + turn visibility).
- Done:
  - Reworked board tile presentation for human readability:
    - compact tile text (`색상`, `구매/렌트`), reduced debug-like wording
    - larger pawn tokens with per-player color for position visibility
    - stronger special tile presentation path retained for `운수`, `종료`
  - Added `TurnStagePanel` to the match main column so non-local actor progress is always visible.
  - Updated responsive board sizing to reduce fixed-size overflow behavior:
    - ring board now uses responsive max width + aspect-ratio layout
    - line board keeps horizontal scroll fallback but reduced minimum size.
  - Added turn-stage styles (badge/cards/grid) for immediate timeline comprehension.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts src/features/board/boardProjection.spec.ts` passed (`24 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - run web test/build and policy gates.
  - continue P0-2 prompt placement/action narration parity fixes.

### Entry 020

- Scope: P0-2 action narration visibility reinforcement.
- Done:
  - Added `실시간 진행` banner in match main column using latest core-lane event.
  - Keeps actor + action label + detail visible even when prompt/theater sections are long.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`21 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue prompt placement parity and non-local turn readability polish.

### Entry 021

- Scope: P0-2 lobby usability parity (collapsible controls).
- Done:
  - Rebuilt `LobbyView` with collapsible sections:
    - 로비 제어
    - 스트림 연결
    - 세션 목록
  - Added shared `panel-head` layout styles for consistent fold controls.
- Validation:
  - `npm run build` passed (`apps/web`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`21 passed`).
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue prompt placement/action narration parity fixes in match flow.

### Entry 022

- Scope: P0-2 prompt payload parity (engine->web) and human-readable prompt options.
- Done:
  - Updated `GPT/viewer/human_policy.py` decision envelopes for human seat prompts:
    - draft/final character choices now include `character_ability` payload.
    - mark target / purchase / geo bonus / coin placement / burden exchange labels localized.
    - hidden-trick prompt now also carries `full_hand` context for unified card rendering.
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx`:
    - movement submit is disabled until valid card-selection combination exists in card mode.
    - trick prompt shows single unified hand summary (`손패 전체`, `히든` count).
    - mark-target card now renders explicit target summary (`대상 인물 / 플레이어`).
- Validation:
  - `python -m py_compile GPT/viewer/human_policy.py` passed.
  - `python -m pytest GPT/test_human_policy_prompt_payloads.py -q` passed (`2 passed`).
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`21 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2 live match UX parity: non-local turn narration/overlay positioning and prompt ergonomics.

### Entry 023

- Scope: P0-2 live match visibility reinforcement (non-local core actions + weather effect fallback).
- Done:
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts`:
    - added safer weather fallback helper (`weatherEffectFallbackText`) so weather effect no longer collapses to `-` when payload effect is omitted.
    - weather reveal/situation persistence now use the fallback helper.
  - Updated `apps/web/src/App.tsx`:
    - added `selectCoreActionFeed(...)` usage in match screen.
    - added a new `최근 핵심 행동 목록` strip (latest 8 core actions) so other players’ moves/purchases/rent flow remains visible in real time.
  - Updated `apps/web/src/styles.css`:
    - added core-action-strip panel/card styles with responsive fallback.
  - Added selector regressions in `apps/web/src/domain/selectors/streamSelectors.spec.ts`:
    - weather fallback text test (missing explicit weather effect payload).
    - core action feed local/non-local actor classification test.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`18 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2/P0-3 parity fixes: replace remaining prompt text corruption and restore human-centric interaction wording.

### Entry 024

- Scope: P0-2 prompt UX readability normalization (human-friendly copy + interaction clarity).
- Done:
  - Rewrote `apps/web/src/features/prompt/PromptOverlay.tsx` with normalized Korean copy and consistent interaction flow:
    - movement prompt now clearly split into `주사위 굴리기` / `주사위 카드 사용`
    - card selection uses concise chip list (`[1] [2] ...`) with max-card guidance
    - trick/hidden-trick cards render in one unified hand view with hidden-state and usability badges
    - draft/final character prompts now display explicit guidance and ability text block
    - mark target prompt renders explicit `[대상 인물 / 플레이어: ...]` description
    - busy/feedback text rewritten to user-facing wording
  - Replaced corrupted prompt label/helper catalogs with UTF-8 clean definitions:
    - `apps/web/src/domain/labels/promptTypeCatalog.ts`
    - `apps/web/src/domain/labels/promptHelperCatalog.ts`
- Validation:
  - `npm run test -- --run src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`24 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
  - `python tools/plan_policy_gate.py` passed.
- Next:
  - Continue P0-2/P0-3: turn-theater narrative polish and prompt/request sequencing parity against engine flow.

### Entry 025

- Scope: P0-3 turn-theater readability normalization.
- Done:
  - Rewrote `apps/web/src/features/theater/IncidentCardStack.tsx` with clean user-facing copy:
    - lane section titles normalized (`핵심 진행`, `선택 / 응답`, `시스템`)
    - tone/lane badges normalized (`이동/경제/중요/진행`, `핵심/선택/시스템`)
    - per-lane fold controls renamed to `접기/펼치기`
    - actor/action row format unified to `Pn - 이벤트`
  - Kept existing lane prioritization logic and focus-player ordering behavior intact.
- Validation:
  - `npm run test -- --run src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`29 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue match-screen copy polish and remaining sequence parity checks (weather/fortune/turn narration consistency).

### Entry 026

- Scope: P0-2 board readability normalization (human-facing copy).
- Done:
  - Rewrote `apps/web/src/features/board/BoardPanel.tsx` while preserving projection logic:
    - tile/zone/cost/owner labels now use player-facing Korean wording
    - special tile labels normalized (`운수`, `종료 - 1`, `종료 - 2`, `고급 토지`)
    - board header summary normalized (`라운드/턴/징표 소유자/종료 시간`)
    - recent move line normalized (`최근 이동: Px a -> b`)
    - pawn rendering and move highlight behavior preserved
  - Kept DI/selectors boundary unchanged (presentation-only refactor).
- Validation:
  - `npm run test -- --run src/features/board/boardProjection.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`29 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2/P0-3 sequence parity and narration quality (weather/fortune/turn theater continuity).

### Entry 027

- Scope: P0-2 prompt-submit reliability hardening (prevent stuck `처리 중` state).
- Done:
  - Updated websocket client send contract:
    - `StreamClient.send(...)` now returns `boolean` success/failure.
    - `StreamClient.requestResume(...)` now returns `boolean` success/failure.
  - Updated hook contract:
    - `useGameStream.sendDecision(...)` now returns `boolean`.
  - Updated match prompt handling in `App.tsx`:
    - prompt busy state is enabled only after a successful decision send.
    - when send fails, immediate user-facing feedback is shown.
    - if prompt is busy and stream transitions to non-connected/error, busy state is released with retry guidance.
- Validation:
  - `npm run test -- --run src/infra/ws/StreamClient.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`16 passed`).
  - `npm run test -- --run src/infra/ws/StreamClient.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts` passed (`23 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2 human-play UX parity pass (prompt narrative clarity + non-local turn continuity polish).

### Entry 028

- Scope: P0-2 prompt choice-card normalization (request-type specific human wording).
- Done:
  - Updated `PromptOverlay` generic choice rendering to apply request-specific text normalization:
    - `lap_reward`: `현금/조각/승점 선택` + 실제 보상 수치 표시
    - `purchase_tile`: `토지 구매` / `구매 없이 턴 종료` 문구 고정
    - `active_flip`: `뒤집기 종료` 및 `A -> B` 변환 문구 고정
    - `burden_exchange`: `지 카드 제거` / `유지` 문구 고정
  - Rewrote `promptSelectors.spec.ts` in clean UTF-8 Korean for readability/maintainability.
- Validation:
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/infra/ws/StreamClient.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts` passed (`26 passed`).
  - `npm run build` passed (`apps/web`).
  - `python tools/encoding_gate.py` passed.
- Next:
  - Continue P0-2/P1 with turn-theater continuity polish and observer/non-local turn visibility flow.

### Entry 029

- Scope: P0-1/P0-2 decision lifecycle visibility cleanup in React selectors.
- Done:
  - Updated `apps/web/src/domain/selectors/promptSelectors.ts`:
    - active prompts now close not only on `decision_ack(accepted|stale)` but also on canonical runtime events:
      - `decision_resolved`
      - `decision_timeout_fallback`
    - this prevents resolved non-local/AI prompts from lingering as if still actionable.
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts`:
    - situation headline now ignores prompt/system noise when selecting the current narrative event:
      - `prompt`
      - `decision_ack`
      - `decision_requested`
      - `decision_resolved`
      - `decision_timeout_fallback`
      - `parameter_manifest`
      - all `error` messages
    - result: `현재 상황` follows core rule progression instead of getting replaced by prompt/ack/runtime warning chatter.
  - Added selector regression coverage:
    - prompt closes when the same request is resolved by event without local ack
    - prompt closes when timeout fallback event arrives
    - situation headline remains pinned to the latest core turn event even if prompt/decision messages arrive later
  - Updated `apps/web/src/features/theater/IncidentCardStack.tsx`:
    - system lane now defaults to collapsed so runtime/debug chatter does not dominate the live match screen by default
- Validation:
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts` passed (`18 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P0-2 with lane rendering/UI so the cleaned selector behavior is reflected as distinct core/prompt/system panels during human play.

### Entry 030

- Scope: P0-2 core-turn action lane wiring in the React match screen.
- Done:
  - Added `apps/web/src/features/theater/CoreActionPanel.tsx`.
    - promotes non-local/public turn actions into a dedicated panel
    - keeps the latest visible action as a larger hero card
    - keeps a short grid of recent public actions underneath
  - Wired `CoreActionPanel` into `apps/web/src/App.tsx` directly under `TurnStagePanel`.
  - Updated `apps/web/src/styles.css`:
    - added dedicated `core-action-panel` / hero / feed-card styles
    - hid legacy `live-action-banner` and `core-action-strip-panel` blocks so the old strip UI does not duplicate the new lane
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue P0-2 with viewport-scale layout, prompt placement, and motion/board readability recovery.

### Entry 031

- Scope: P0-2 viewport-scale match layout and prompt overlay sizing recovery.
- Done:
  - Updated `apps/web/src/styles.css` so the live match screen uses the viewport more aggressively:
    - wider `match-layout` split
    - sticky side column on desktop
    - board scroll region capped against viewport height instead of forcing oversized page growth
    - ring board now scales by viewport height/width rather than a fixed `980px` ceiling
  - Prompt overlay now opens closer to full viewport width/height instead of the previous narrower fixed ceiling.
  - Added hover/transition polish for tile cards and prompt choice cards to improve scanability/click affordance.
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - remove the remaining duplicated legacy action JSX from `App.tsx`
  - continue prompt placement separation and theater-grade movement/purchase/fortune rendering

### Entry 032

- Scope: P0-2 prompt presentation separation polish.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so the overlay root carries a request-type class (`prompt-overlay-${requestType}`).
  - Updated `apps/web/src/styles.css`:
    - prompt modal now behaves more like a bottom-sheet layer instead of always centering over the full board
    - request-type overlays (`movement`, `trick_to_use`, `hidden_trick_card`, `mark_target`) can now size differently
    - choice cards and primary action buttons received clearer hover affordances
    - desktop prompt choice density was increased while keeping mobile single-column fallback
- Validation:
  - `npm run build` passed (`apps/web`).
- Remaining:
  - remove leftover duplicated legacy action JSX in `App.tsx`
  - continue actor-turn / movement / purchase / fortune theater rendering

### Entry 033

- Scope: P0-2 turn-theater readability uplift.
- Done:
  - Rewrote `apps/web/src/features/theater/IncidentCardStack.tsx` in clean UTF-8 Korean labels.
  - Added a hero-style top card for the latest core/public action.
  - Reframed lane labels to player-facing wording:
    - `턴 진행`
    - `선택 요청`
    - `시스템 기록`
  - Updated `apps/web/src/styles.css` for stronger incident theater hierarchy:
    - hero card
    - clearer card spacing
    - stronger emphasis state for current/high-priority core events
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue movement / purchase / fortune / rent visualization upgrades
  - clean remaining legacy duplicated JSX in `App.tsx`

### Entry 034

- Scope: P0-2 stage summary hierarchy and board pawn readability.
- Done:
  - Rewrote `apps/web/src/features/stage/TurnStagePanel.tsx` in clean UTF-8 Korean with a stronger hierarchy:
    - hero card for current actor/turn
    - dedicated weather card
    - separate movement / landing / card-effect summaries
  - Updated `apps/web/src/features/board/BoardPanel.tsx` so pawn tokens now render the player number directly inside the token.
  - Updated `apps/web/src/styles.css`:
    - larger pawn tokens
    - stronger stage-panel layout and card hierarchy
    - mobile fallback for the stage hero card
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue theater-grade rendering for movement / purchase / fortune / rent
  - remove remaining duplicated legacy action JSX in `App.tsx`

### Entry 035

- Scope: P0-2 public-action wording cleanup and event tone alignment.
- Done:
  - Rewrote `apps/web/src/features/theater/CoreActionPanel.tsx` in clean UTF-8 Korean.
  - Clarified public-action copy so the panel explicitly describes visible shared actions.
  - Updated `apps/web/src/domain/labels/eventToneCatalog.ts`:
    - `rent_paid`, `fortune_drawn`, `fortune_resolved` now follow economy tone
    - `trick_used` now follows critical tone for stronger visibility in theater cards
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue movement / purchase / fortune / rent card-specific rendering
  - remove remaining duplicated legacy action JSX in `App.tsx`

### Entry 036

- Scope: P0-2 public-action card scanning aids.
- Done:
  - Updated `apps/web/src/features/theater/CoreActionPanel.tsx`:
    - added a lightweight action-type classifier for player-facing chips
    - cards now surface `이동 / 경제 / 효과 / 선택 / 진행` categories directly in metadata
  - Updated `apps/web/src/styles.css` with `core-action-chip` styling for faster card scanning
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue per-action rendering improvements
  - remove remaining duplicated legacy action JSX in `App.tsx`

### Entry 037

- Scope: P0-2 theater component UTF-8 recovery and stronger action differentiation.
- Done:
  - Rewrote these files in clean UTF-8 Korean:
    - `apps/web/src/features/theater/CoreActionPanel.tsx`
    - `apps/web/src/features/theater/IncidentCardStack.tsx`
  - Added action-kind differentiation in public action cards:
    - `move`
    - `economy`
    - `effect`
    - `decision`
    - `system`
  - Added matching border-accent styling in `apps/web/src/styles.css`.
  - In `apps/web/src/App.tsx`, duplicated legacy action render paths were disabled from actual rendering (`false ? (...) : null`) so only the new panels remain visible.
- Validation:
  - `npm run build` passed (`apps/web`).
- Remaining:
  - physically remove the disabled legacy JSX block from `App.tsx`
  - continue per-event bespoke rendering for movement / purchase / fortune / rent

### Entry 038

- Scope: P0-2 duplicated action render cleanup and theater card differentiation.
- Done:
  - Physically removed the remaining disabled legacy public-action JSX blocks from `apps/web/src/App.tsx`.
  - Rewrote these files in clean UTF-8 with player-facing Korean copy:
    - `apps/web/src/features/theater/CoreActionPanel.tsx`
    - `apps/web/src/features/theater/IncidentCardStack.tsx`
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
  - Strengthened public-action cards so movement / economy / effect / decision / system items now render with different copy structure and detail blocks.
  - Added theater lane subtitles so `turn progress / prompt flow / system log` remain visually distinct.
  - Updated `apps/web/src/styles.css` with:
    - `core-action-detail-list`
    - `core-action-detail-item`
    - `incident-lane-subtitle`
- Validation:
  - `npm run build` passed (`apps/web`).
- Next:
  - continue actor-flow continuity so other-player turns feel more cinematic
  - keep reducing replay-like feeling in the live match screen

### Entry 039

- Scope: current-work snapshot organization + string externalization planning.
- Done:
  - Added active plan `PLAN/[PLAN]_STRING_RESOURCE_EXTERNALIZATION_AND_ENCODING_STABILITY.md`.
  - Linked the plan into priority/status/mandatory reading docs.
  - Recorded the reason for the new plan: repeated mojibake risk and inline-string regression across React runtime surfaces.
  - Kept the current snapshot push-oriented rather than pretending the live UX recovery is complete.
- Validation:
  - existing `apps/web` build remains passing from the current UI slice.
- Next:
  - extract critical live-view strings from `App.tsx`, theater, stage, prompt, and lobby components before further UX reshaping.
