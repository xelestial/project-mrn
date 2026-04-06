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

### Entry 040

- Scope: P0-string phase 1 implementation and verification.
- Done:
  - Added centralized typed resource ownership in `apps/web/src/domain/text/uiText.ts`.
  - Migrated major visible React strings to shared catalogs in:
    - `App.tsx`
    - `LobbyView.tsx`
    - `PromptOverlay.tsx`
    - `CoreActionPanel.tsx`
    - `IncidentCardStack.tsx`
    - `TurnStagePanel.tsx`
    - `BoardPanel.tsx`
    - `ConnectionPanel.tsx`
  - Replaced remaining direct join-seat error text in `App.tsx` with catalog-driven wording.
  - Normalized lobby chrome wording to player-facing Korean labels.
- Validation:
  - `npm run test -- --run src/domain/labels` passed (`17 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue P1 string migration into selector-generated visible summaries (`streamSelectors.ts` and adjacent runtime-facing summary helpers).

### Entry 041

- Scope: P0-string phase 2 selector-summary migration.
- Done:
  - Added shared `STREAM_TEXT` helpers to `apps/web/src/domain/text/uiText.ts`.
  - Migrated selector-facing visible phrases in `apps/web/src/domain/selectors/streamSelectors.ts`:
    - generic event fallback
    - weather effect fallback text
    - move/dice summaries
    - landing result labels
    - heartbeat detail text
    - runtime stalled warning text
    - tile purchase / marker transfer summaries
    - bankruptcy / game-end winner summaries
    - lap reward summary pieces
    - manifest sync / mark resolved / marker flip / 종료 시간 변경 text
    - prompt waiting summary in turn-stage projection
  - Fixed `decision_ack` non-event label regression back to `선택 응답`.
- Validation:
  - `npm run test -- --run src/domain/labels src/domain/selectors` passed (`35 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - Continue remaining string ownership cleanup in theater classification heuristics and any leftover board/runtime display literals.

### Entry 042

- Scope: priority reference UTF-8 recovery.
- Done:
  - Rewrote `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md` in clean UTF-8.
  - Re-aligned the document with current actual priorities:
    - Unified Decision API stability
    - Human Play live UI recovery
    - latest game-rule alignment
    - string externalization / encoding stability
- Validation:
  - document rewritten as plain UTF-8 text and now usable as the current start-order reference.
- Next:
  - continue remaining P0-string cleanup and then return to live human-play UI recovery tasks using the refreshed priority reference.

### Entry 043

- Scope: P0-string phase 3 prompt/auxiliary catalog consolidation.
- Done:
  - Expanded `apps/web/src/domain/text/uiText.ts` with:
    - `PLAYERS_TEXT`
    - `TIMELINE_TEXT`
    - `PROMPT_TYPE_TEXT`
    - `PROMPT_HELPER_TEXT`
  - Rewired these modules to consume centralized text resources:
    - `apps/web/src/domain/labels/promptTypeCatalog.ts`
    - `apps/web/src/domain/labels/promptHelperCatalog.ts`
    - `apps/web/src/features/players/PlayersPanel.tsx`
    - `apps/web/src/features/timeline/TimelinePanel.tsx`
  - Recovered corrupted spec files in clean UTF-8:
    - `promptTypeCatalog.spec.ts`
    - `promptHelperCatalog.spec.ts`
    - `uiText.spec.ts`
  - Removed remaining direct mark-target helper copy in `PromptOverlay.tsx` and routed it through prompt helper text.
- Validation:
  - pending local test/build run after this consolidation pass.
- Next:
  - run `apps/web` test/build verification
  - continue remaining selector-string cleanup
  - then return to live human-play UI recovery

### Entry 044

- Scope: P0-string phase 4 leftover selector/display cleanup.
- Done:
  - Removed duplicated weather fallback ownership from `streamSelectors.ts` so selector weather fallback now depends only on `STREAM_TEXT`.
  - Moved board zone-color CSS aliases into `BOARD_TEXT.zoneColorCss`.
  - Rewired `BoardPanel.tsx` to consume the centralized board color catalog.
- Validation:
  - pending local test/build run after this leftover cleanup.
- Next:
  - re-run `apps/web` tests/build
  - if clean, shift focus back to human-play live UI recovery

### Entry 045

- Scope: P0-2 situation panel readability recovery.
- Done:
  - Added `SITUATION_TEXT` to the shared UI text catalog.
  - Rebuilt `apps/web/src/features/status/SituationPanel.tsx` as a card-based summary panel:
    - 행동자
    - 라운드 / 턴
    - 현재 이벤트
    - 이번 라운드 날씨
    - 날씨 효과
  - Added matching layout styles in `apps/web/src/styles.css` so the situation area reads like a live match summary instead of raw stacked lines.
- Validation:
  - pending local build/test after the panel rewrite.
- Next:
  - verify `apps/web` build/test
  - continue human-play theater/live-flow improvements

### Entry 046

- Scope: P0-string UTF-8 catalog recovery and selector label stabilization.
- Done:
  - Rebuilt `apps/web/src/domain/text/uiText.ts` in clean UTF-8 with restored Korean wording for:
    - app/lobby/connection/board/player/timeline/situation text
    - prompt type/helper text
    - stream/theater/turn-stage/prompt text
  - Rebuilt `apps/web/src/domain/labels/eventLabelCatalog.ts` in clean UTF-8.
  - Recovered corrupted spec files in clean UTF-8:
    - `uiText.spec.ts`
    - `eventLabelCatalog.spec.ts`
    - `promptTypeCatalog.spec.ts`
    - `promptHelperCatalog.spec.ts`
    - `streamSelectors.spec.ts`
- Validation:
  - `npm run test -- --run src/domain/text src/domain/labels src/domain/selectors` passed (`43 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - continue remaining string ownership cleanup by moving event labels into the shared catalog layer
  - keep pushing live human-play stage continuity

### Entry 047

- Scope: P0-string shared event-label ownership + P0-2 turn-stage continuity.
- Done:
  - Added `EVENT_LABEL_TEXT` to `apps/web/src/domain/text/uiText.ts`.
  - Rewired `apps/web/src/domain/labels/eventLabelCatalog.ts` to consume shared text resources instead of owning inline labels.
  - Extended `selectTurnStage` in `apps/web/src/domain/selectors/streamSelectors.ts` with:
    - `currentBeatLabel`
    - `currentBeatDetail`
    - turn-progress trail seeded from `turn_start`
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` to render:
    - current live beat card
    - prompt/current-action summary
    - visible turn-progress trail chips
  - Added matching trail/wide-card styles in `apps/web/src/styles.css`.
- Validation:
  - `npm run test -- --run src/domain/text src/domain/labels src/domain/selectors` passed.
  - `npm run build` passed (`apps/web`).
- Next:
  - keep reducing “replay/debug wall” feel by making other-player turn beats more theatrical
  - continue prompt UX tightening and board/readability recovery

### Entry 048

- Scope: P0-string UTF-8 catalog hard recovery + browser quick-start parity lock.
- Done:
  - Fully restored `apps/web/src/domain/text/uiText.ts` in clean UTF-8 Korean/English.
  - Recovered corrupted spec files in clean UTF-8:
    - `apps/web/src/domain/text/uiText.spec.ts`
    - `apps/web/src/domain/labels/promptTypeCatalog.spec.ts`
    - `apps/web/src/domain/labels/promptHelperCatalog.spec.ts`
    - `apps/web/src/domain/labels/eventLabelCatalog.spec.ts`
    - `apps/web/src/domain/selectors/streamSelectors.spec.ts`
  - Extended `apps/web/e2e/parity.spec.ts` with a real `1 human + 3 AI quick start` browser flow:
    - `POST /sessions`
    - `POST /join`
    - `POST /start`
    - runtime polling
    - stream replay
    - first human prompt visibility
  - Updated existing browser parity assertions so they match the current Korean lobby/match UI instead of stale English/raw-debug assumptions.
- Validation:
  - `npm run test -- --run src/domain/text src/domain/labels src/domain/selectors` passed (`43 passed`).
  - `npm run e2e -- e2e/parity.spec.ts` passed (`4 passed`).
  - `npm run build` passed (`apps/web`).
- Next:
  - keep pushing P0-2 live-play UX so prompt surfaces feel like a game, not a debug inspector
  - add more mixed-session browser coverage for follow-up human decisions (`movement`, `purchase_tile`, `mark_target`)

### Entry 049

- Scope: mandatory encoding-safety rule reinforcement.
- Done:
  - Rewrote `docs/engineering/[MANDATORY]_PRINCIPLES_AND_REQUIRED_PLAN_READING.md` in clean UTF-8.
  - Added an absolute start rule so every task must open the mandatory reading document first.
  - Strengthened the encoding policy:
    - Korean text must stay UTF-8
    - CP-949 is forbidden
    - PowerShell mojibake must not trigger ad-hoc file re-encoding
  - Updated `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md` so every future task explicitly re-checks:
    - mandatory principles
    - string/externalization plan
- Validation:
  - documentation update only
- Next:
  - continue P0-2 live-play UX recovery on top of the stabilized encoding/documentation rules

### Entry 050

- Scope: P0-2 prompt-surface recovery for movement / purchase / mark, plus browser parity lock.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so key human prompts render as dedicated game-style cards instead of falling back to one generic choice wall:
    - `movement`
      - now parses both runtime-contract `dice_*` ids and `card_values` payloads
      - shows context cards (`현재 위치`, `사용 가능 카드`, `선택 카드`, `현재 날씨`)
      - exposes stable `data-testid` hooks for browser verification
    - `purchase_tile`
      - now renders a dedicated decision layout with tile/cost/cash/zone summary cards
      - action cards are emphasized as `토지 구매` vs `구매 없이 턴 종료`
    - `mark_target`
      - now renders actor/candidate/location context cards
      - target cards stay explicit about `대상 인물 / 플레이어`
    - `lap_reward`
      - now renders a dedicated reward-choice surface with current resource summaries
  - Updated `apps/web/src/styles.css` with prompt context grids and stronger dedicated choice layouts for target/purchase/reward decisions.
  - Extended `apps/web/e2e/parity.spec.ts` with new browser coverage:
    - movement prompt contract path using `dice_1_4`
    - purchase decision prompt
    - mark target prompt
- Validation:
  - `npm run test -- --run src/domain/selectors src/domain/labels src/domain/text` passed (`43 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - continue P0-2 on non-local turn choreography so other-player actions feel live, not replay-like
  - keep shrinking prompt inspector feel by moving more context into stage/theater cards and less into large static walls

### Entry 051

- Scope: P0-2 non-local turn continuity recovery between stage, board, and core-action summaries.
- Done:
  - Extended `apps/web/src/domain/selectors/streamSelectors.ts` so `selectTurnStage` now carries:
    - `currentBeatKind`
    - `focusTileIndex`
  - Beat kind is now projected from canonical event codes:
    - `move`
    - `economy`
    - `effect`
    - `decision`
    - `system`
  - Tile focus is now derived from canonical payload fields for:
    - `player_move`
    - `landing_resolved`
    - `tile_purchased`
    - `rent_paid`
    - `fortune_drawn`
    - `fortune_resolved`
    - `trick_used`
    - actionable prompt context with `public_context.tile_index`
  - Updated `apps/web/src/features/board/BoardPanel.tsx` so the board can render a live focus summary and focus-ring overlay that follows the current turn beat.
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` and `apps/web/src/styles.css` so hero/current-beat cards change emphasis by beat kind instead of always looking identical.
  - Filled a real selector UX hole:
    - `rent_paid` details are now summarized explicitly instead of falling through as empty text
    - `fortune_drawn` / `fortune_resolved` now also emit explicit summary strings through the shared text catalog
  - Added selector regression coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts` for:
    - purchase focus
    - rent focus
    - prompt-driven focus carry-over
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`19 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - keep pushing P0-2 by making the other-player turn read more like `actor start -> move -> landing -> result` instead of isolated cards
  - strengthen weather / fortune persistence so it feels like live board state, not just one summary field

### Entry 052

- Scope: P0-2 focused board readability follow-up.
- Done:
  - Added an in-tile live action tag to `apps/web/src/features/board/BoardPanel.tsx` so the currently focused board tile now shows the active beat label directly on the square.
  - Added beat-colored focus styling in `apps/web/src/styles.css` so the board summary and the focused tile share the same move/economy/effect/decision language.
  - Updated `pickMessageDetail` in `apps/web/src/domain/selectors/streamSelectors.ts` so `turn_start` no longer produces an empty detail line in stage/theater summaries.
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`14 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - keep reducing the gap between "highlighted tile" and "felt turn flow" by chaining actor start / move / landing / result more explicitly across stage and theater

### Entry 053

- Scope: P0-2 turn-flow visibility + board-weather persistence + browser regression coverage.
- Done:
  - Added persistent board weather summary to `apps/web/src/features/board/BoardPanel.tsx` so the current round weather remains visible near the board even when the user is focused on turn actions.
  - Added a per-tile live action tag for the currently focused board tile so the player can see not just which tile is active, but what kind of beat is being processed there.
  - Extended `apps/web/src/features/theater/CoreActionPanel.tsx` with a same-turn flow panel:
    - it now shows the latest turn's public sequence as a short ordered strip instead of only isolated recent cards
  - Extended `CoreActionItem` with canonical event metadata (`eventCode`, `round`, `turn`) so the UI can group public actions by actual turn boundaries.
  - Added browser test coverage in `apps/web/e2e/parity.spec.ts` so the quick-start smoke now verifies:
    - `board-weather-summary`
    - `core-action-flow-panel`
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts` passed (`19 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
  - `npm run build` passed (`apps/web`)
- Next:
  - continue toward full human-play feel by making non-local turns animate/read as one continuous scene instead of a better-organized live log

### Entry 054

- Scope: P0-string UTF-8 catalog recovery + P0-2 spectator continuity.
- Done:
  - Rewrote `apps/web/src/domain/text/uiText.ts` as a clean UTF-8 resource catalog.
  - Rewrote `apps/web/src/domain/text/uiText.spec.ts` so string-catalog regression checks now assert human-readable Korean instead of mojibake snapshots.
  - Added `apps/web/src/features/stage/SpectatorTurnPanel.tsx`.
  - Replaced the old waiting-only panel in `apps/web/src/App.tsx` with the spectator turn panel so non-local turns now keep showing:
    - current weather
    - current beat
    - latest public action
    - move / landing / economy / effect summaries
    - turn progress trail
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
- Next:
  - continue recovering prompt-surface copy/layout so the movement / trick / mark / purchase prompts stop inheriting legacy broken inline strings
  - add browser-level coverage for spectator-side continuity when it is not the local player's turn

### Entry 055

- Scope: bilingual string architecture planning.
- Done:
  - Added `PLAN/[PLAN]_BILINGUAL_STRING_RESOURCE_ARCHITECTURE.md`.
  - Defined a locale-split architecture so Korean/English strings can be stored outside components and injected through a provider layer.
  - Covered:
    - target directory layout under `apps/web/src/i18n/`
    - locale bundle composition
    - translator/provider usage model
    - selector detachment from locale-specific sentence ownership
    - migration order
    - parity/e2e test requirements
- Next:
  - after the current prompt-surface cleanup, start the i18n foundation:
    - `apps/web/src/i18n/`
    - `ko/en` locale skeletons
    - `uiText.ts` compatibility bridge

### Entry 056

- Scope: priority-board resync + locale-boundary execution start.
- Done:
  - Re-synced active plan documents so current implementation is no longer driven by already-completed "add i18n foundation" tasks.
  - Updated the live priority order to:
    - selector/resource locale detachment
    - prompt cleanup on top of locale resources
    - non-local turn continuity
    - rule-parity visual fixes
  - Marked `apps/web/src/i18n/` foundation as already active and narrowed the string plan to:
    - selector-visible phrasing
    - compatibility-bridge reduction
    - locale-aware resource ownership
  - Prepared the next execution slice around `streamSelectors.ts` so visible wording can stop depending on the Korean bridge by default.
- Validation:
  - document/status resync only
- Next:
  - add locale-aware text injection path to `streamSelectors.ts`
  - wire `App.tsx` to pass current locale resources into selector formatting
  - keep browser/test coverage green while reducing `uiText.ts` ownership

### Entry 057

- Scope: P0-4 selector locale-boundary implementation.
- Done:
  - Added locale-aware text injection to `apps/web/src/domain/selectors/streamSelectors.ts`.
  - Added `StreamSelectorTextResources` and kept a default compatibility path for existing tests/callers.
  - Moved runtime selector formatting away from forced Korean bridge ownership for:
    - timeline
    - theater feed
    - critical alerts
    - situation
    - turn stage
    - core action feed
  - Updated `apps/web/src/App.tsx` so live runtime selectors receive the current locale resources from `useI18n()`.
  - Re-synced the active string/priority plans to reflect that selector locale injection is now in place.
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/labels/eventLabelCatalog.spec.ts src/domain/labels/promptTypeCatalog.spec.ts src/domain/labels/promptHelperCatalog.spec.ts src/domain/text/uiText.spec.ts` passed (`33 passed`)
  - `npm run e2e -- e2e/parity.spec.ts` passed (`6 passed`)
- Next:
- continue shrinking selector-owned visible sentence composition
- keep prompt/theater/runtime surfaces aligned with locale resources
- move further toward human-play-first match UX on top of the locale-safe selector path

### Entry 058

- Scope: P0-2 browser-level human-play recovery hardening.
- Done:
  - Added stable test ids for:
    - quick-start lobby button
    - turn notice banner
    - spectator turn detail cards
  - Added `apps/web/e2e/human_play_runtime.spec.ts` with dedicated UTF-8-safe browser coverage for:
    - quick start -> first local prompt visible
    - remote actor turn -> spectator panel visible and no local prompt
- Why:
  - core human-play flow should not depend on brittle direct locale text matching
  - this protects against regressions in:
    - local actionable prompt visibility
    - remote turn continuity
    - turn-start feedback visibility
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 059

- Scope: P0-2 prompt surface cleanup and spectator continuity uplift.
- Done:
  - Reworked `apps/web/src/features/prompt/PromptOverlay.tsx` so the local decision surface now separates:
    - header/instruction
    - choice body
    - low-priority request metadata/footer
  - Added section wrappers and stronger choice-surface styling in `apps/web/src/styles.css` to reduce the remaining inspector/debug feel.
  - Upgraded `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now shows:
    - current weather
    - weather effect
    - current character
    - current beat
    - latest public action
  - Extended browser coverage in `apps/web/e2e/human_play_runtime.spec.ts` to assert the spectator character card is present.
- Why:
  - human play still suffered from a "form inspector" feeling during prompts
  - remote turns needed faster comprehension of "who is acting as what under which weather"
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 060

- Scope: P0-2 top-shell cleanup and passive/observer guidance polish.
- Done:
  - Reworked `apps/web/src/features/status/ConnectionPanel.tsx` into a compact status-card grid so the connection shell reads like a game HUD instead of a debug paragraph block.
  - Updated `apps/web/src/App.tsx` passive-prompt surface so other-player decision waiting is shown as a compact observer card with a spinner badge instead of plain text.
  - Extended `apps/web/src/styles.css` to support:
    - connection HUD cards
    - cleaner sticky top shell background
    - stronger passive prompt presentation
  - Kept the human-play browser/runtime regression green after the shell changes.
- Why:
  - the top area still pulled visual attention away from the actual board/gameplay scene
  - passive waiting feedback needed to feel like "someone else is deciding" rather than "a debug paragraph happened"
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 061

- Scope: P0-2 observer continuity follow-up.
- Done:
  - Extended `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now also surfaces:
    - current weather effect
    - current prompt/choice state
  - Added a stable `spectator-turn-prompt` browser hook.
  - Updated locale resources in:
    - `apps/web/src/i18n/locales/ko.ts`
    - `apps/web/src/i18n/locales/en.ts`
  - Kept browser coverage aligned in `apps/web/e2e/human_play_runtime.spec.ts`.
- Why:
  - remote-turn readability still dropped whenever there was a lull between public actions
  - human observers need to know whether the remote player is moving, resolving, or currently deciding
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 062

- Scope: P0-2 board scene readability follow-up.
- Done:
  - Upgraded the focused tile surface in `apps/web/src/features/board/BoardPanel.tsx` so the live tag now shows:
    - beat label
    - beat detail
  - Added pulsing emphasis by beat kind in `apps/web/src/styles.css` for:
    - move
    - economy
    - effect
    - decision
- Why:
  - board focus previously showed that a tile mattered, but not clearly why it mattered
  - human observers need the board itself to explain the scene, not only the side/theater panels
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 063

- Scope: P0-2 board actor/move scene follow-up.
- Done:
  - Extended `apps/web/src/features/board/BoardPanel.tsx` so the focused board scene now exposes:
    - explicit move-start badge
    - explicit move-end badge
    - current active-turn actor banner on the relevant tile
  - Added locale-backed board strings in:
    - `apps/web/src/i18n/locales/ko.ts`
    - `apps/web/src/i18n/locales/en.ts`
    for:
    - move start
    - move end
    - active actor tag
  - Expanded `apps/web/src/styles.css` so:
    - move badges are visually anchored to the tile corner
    - the active pawn pulses more strongly
    - the active-turn tile now carries a small live actor banner
  - Tightened browser regression in `apps/web/e2e/human_play_runtime.spec.ts` to verify:
    - `board-move-start-badge`
    - `board-move-end-badge`
    - `board-actor-banner`
- Why:
  - human observers still had to infer too much from side panels instead of reading the board directly
  - movement continuity is more legible when the board explicitly marks origin, destination, and active actor
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 064

- Scope: P0-2 movement/mark prompt simplification follow-up.
- Done:
  - Simplified the movement decision surface in `apps/web/src/features/prompt/PromptOverlay.tsx` so it now reads as:
    - short instruction
    - compact current context
    - mode switch
    - selected-state pills
    - execute button
    instead of repeating multiple context card blocks.
  - Added movement status-pill styling in `apps/web/src/styles.css` so card-mode selection no longer feels like a raw inspector dump.
  - Upgraded mark-target choice cards in `apps/web/src/features/prompt/PromptOverlay.tsx` to expose:
    - target character
    - target player id
    as direct choice pills instead of relying only on descriptive text.
- Why:
  - human decision prompts still spent too much vertical space on duplicated metadata
  - mark-target selection needed more glanceable "who exactly is this target" information
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 065

- Scope: P0-2 public turn-flow choreography follow-up.
- Done:
  - Upgraded `apps/web/src/features/theater/CoreActionPanel.tsx` so the latest same-turn public actions now render as a compact journey strip, not only as isolated cards.
  - Added journey-strip styling in `apps/web/src/styles.css` so move/economy/effect/decision beats read like a chained scene.
  - Extended browser regression in `apps/web/e2e/human_play_runtime.spec.ts` to lock `core-action-journey` during remote-turn viewing.
- Why:
  - remote turns still felt too much like a card log
  - same-turn public events need to read as one unfolding scene for human observers
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 066

- Scope: P0-2/P0-4 runtime stabilization in forced English mode.
- Done:
  - Switched `apps/web/src/i18n/index.ts` default locale to `en`.
  - Tightened `apps/web/src/i18n/I18nProvider.tsx` initial-locale resolution so the app now boots into English unless the stored locale is already `en`.
  - Preserved the in-progress turn-stage scene-strip / public-turn flow work while re-stabilizing runtime behavior.
  - Cleaned temporary Playwright output under `apps/web/test-results/`.
- Why:
  - the Korean locale recovery path is still in progress and should not block runtime verification
  - human-play validation needs one stable language mode that can keep build, selector tests, and browser parity green
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 067

- Scope: P0-2/P0-4 prompt readability cleanup and turn-scene continuity.
- Done:
  - Cleaned `apps/web/src/features/prompt/PromptOverlay.tsx` so visible prompt context no longer shows corrupted unit suffixes.
  - Reduced prompt inspector feel in English mode by:
    - removing bracket-heavy copy
    - simplifying request meta to actor/time information
    - making dice-card chips render as plain card numbers
  - Extended `apps/web/src/features/stage/TurnStagePanel.tsx` scene-strip so it now carries:
    - move
    - landing
    - purchase
    - rent
    - fortune
  - Added move-tone scene styling in `apps/web/src/styles.css`.
  - Updated `apps/web/src/i18n/locales/en.ts` so English-mode labels read naturally during:
    - trick selection
    - character selection
    - mark targeting
    - locale switching
- Why:
  - human-play prompts still contained debug-ish wording and broken suffix text
  - remote turns needed stronger continuous scene beats so they read less like isolated state cards
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 068

- Scope: P0-2 theater de-duplication and spectator readability follow-up.
- Done:
  - Removed the duplicate same-turn flow panel from `apps/web/src/features/theater/CoreActionPanel.tsx` so the public action area now relies on:
    - latest hero action
    - same-turn journey strip
    - older public action feed
    instead of rendering the same flow twice.
  - Added `data-testid="core-action-panel"` and updated browser coverage to anchor on the panel itself rather than requiring a journey strip in turn states that do not yet have one.
  - Refined `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so:
    - current beat title
    - current beat detail
    - latest public action title
    - latest public action detail
    render on separate lines instead of slash-joined inspector text.
  - Polished English prompt copy in `apps/web/src/i18n/locales/en.ts`:
    - lighter request meta
    - cleaner decision chip wording
    - less mechanical movement / trick / mark / purchase copy
    - simpler busy state text
  - Restyled prompt footer metadata in `apps/web/src/styles.css` into a compact HUD pill instead of raw footer text.
- Why:
  - the match screen still felt too much like a state inspector because the same turn flow was rendered more than once
  - spectator cards still packed multiple ideas into one slash-delimited line
  - prompt footer/status text still read more like transport metadata than live game UI
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 069

- Scope: P0-2 prompt HUD timing follow-up.
- Done:
  - Added a live countdown bar to `apps/web/src/features/prompt/PromptOverlay.tsx` so actionable prompts now show time pressure as a visible HUD element instead of only footer text.
  - Restyled the prompt footer in `apps/web/src/styles.css` so actor/time metadata reads as a compact pill plus timer bar instead of raw inspector text.
- Why:
  - even after wording cleanup, the prompt footer still felt like transport metadata rather than a live game decision surface
  - human testing benefits from seeing countdown pressure immediately, not reconstructing it from text
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`27 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 070

- Scope: P0-2/P0-3 weather selector parity follow-up.
- Done:
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so weather summaries now honor `effect_text` when the runtime payload provides it.
  - Added selector coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts` to lock `weather_reveal.effect_text` parity.
- Why:
  - weather cards must show the actual rule text from the runtime when it exists, not fall back to a generic effect label
  - this directly affects whether live human-play feels trustworthy during round start
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`28 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 071

- Scope: P0-1 unified decision runtime wrapper for AI seats.
- Done:
  - Added `apps/server/src/services/decision_gateway.py`.
  - Moved canonical human decision request/resolve publishing into `DecisionGateway`.
  - Replaced the human-only runtime bridge with `_ServerDecisionPolicyBridge` in `apps/server/src/services/runtime_service.py`.
  - Runtime now wraps both human and AI seats behind one decision contract at the server boundary.
  - AI decisions now emit:
    - `decision_requested`
    - `decision_resolved`
    with `provider="ai"`.
  - Human decision events now explicitly emit `provider="human"`.
  - Added backend regression coverage proving AI purchase decisions emit ordered request/resolve events.
- Why:
  - the runtime previously used one contract for human seats and direct policy calls for AI seats
  - this was the main P0-1 architectural gap still left open in live/runtime mode
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py` passed (`9 passed`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 072

- Scope: P0-2 human-play noise control after AI decision unification.
- Done:
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so AI-side decision lifecycle events are routed to the `system` lane instead of the `prompt` lane.
  - Added selector coverage to lock this behavior.
- Why:
  - AI now shares the same backend decision contract, but those internal request/resolve events should not visually compete with actionable human prompts
- Validation:
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 073

- Scope: P0-2 remote-turn board continuity / move-path visibility.
- Done:
  - Extended `selectLastMove()` in `apps/web/src/domain/selectors/streamSelectors.ts` so recent `player_move` state now preserves the emitted `path` tiles, not only start/end.
  - Updated `apps/web/src/features/board/BoardPanel.tsx` to render recent path-step markers on intermediate tiles during the latest move.
  - Added board styling in `apps/web/src/styles.css` for:
    - intermediate move-trail tiles
    - dashed recent-path emphasis
    - numbered path-step badges
  - Updated `apps/web/e2e/human_play_runtime.spec.ts` so remote-turn runtime coverage now asserts an intermediate path step is visible on the board.
  - Added selector coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts` to lock `pathTileIndices` extraction.
- Why:
  - remote turns still felt too much like card/log updates because only the source and destination tiles were highlighted
  - preserving and rendering the path makes other-player turns read more like spatial movement on a board
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 074

- Scope: P0-1 canonical decision payload follow-up for stream timeout/ack paths.
- Done:
  - Added shared decision payload builders to `apps/server/src/services/decision_gateway.py`:
    - `build_decision_ack_payload(...)`
    - `build_decision_requested_payload(...)`
    - `build_decision_resolved_payload(...)`
    - `build_decision_timeout_fallback_payload(...)`
  - Refactored `DecisionGateway` itself to use those builders instead of ad-hoc inline dictionaries.
  - Updated `apps/server/src/routes/stream.py` so:
    - websocket timeout fallback emission
    - seat decision acknowledgement emission
    now use the same canonical payload builders.
  - Human-side `decision_ack`, `decision_resolved`, and `decision_timeout_fallback` messages now explicitly carry `provider="human"` on the stream route path as well.
  - Added/updated backend regression coverage in:
    - `apps/server/tests/test_runtime_service.py`
    - `apps/server/tests/test_stream_api.py`
- Why:
  - AI-seat runtime wrapping was already emitting canonical lifecycle events, but stream timeout/ack code paths still hand-built similar payloads
  - centralizing those payloads lowers drift risk and moves the system closer to a true shared human/AI decision contract
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed (`9 passed, 13 skipped`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts` passed (`17 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 075

- Scope: P0-2 turn-journey readability follow-up.
- Done:
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` so the scene strip now includes prompt/decision state in the same ordered journey as move / landing / purchase / rent / fortune.
  - Added scene-step numbering to the turn-stage strip.
  - Updated `apps/web/src/styles.css` to style the numbered scene-step badge.
- Why:
  - remote turns still needed a clearer read order for `choose -> move -> land -> resolve`
  - adding prompt state into the same strip makes the turn feel more like one continuous scene instead of disconnected cards
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 076

- Scope: P0-2 outcome-card staging and prompt HUD simplification follow-up.
- Done:
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` so purchase / rent / fortune / trick results now also render as a dedicated outcome strip instead of only living inside mixed summary cards.
  - Updated `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now includes a spotlight row for public economy/effect outcomes.
  - Updated `apps/web/src/features/theater/CoreActionPanel.tsx` so the latest economy/effect beat gets a dedicated result card in addition to the hero/journey/feed layout.
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so collapsed prompt chip text and footer meta use a shorter local HUD line instead of request/debug-heavy wording.
  - Extended browser parity in `apps/web/e2e/human_play_runtime.spec.ts` to lock:
    - `spectator-turn-spotlight`
    - `core-action-result-card`
    - `turn-stage-outcome-strip`
- Why:
  - remote/public turns still needed stronger scene payoff after movement finished
  - prompt surfaces still carried more metadata weight than necessary for human play
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts` passed (`22 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 077

- Scope: P0-2 board move-trail animation follow-up.
- Done:
  - Updated `apps/web/src/features/board/BoardPanel.tsx` so recent path-step badges now carry a step-order CSS variable.
  - Updated `apps/web/src/styles.css` so intermediate move-trail tiles and path-step badges animate in a staggered wave instead of remaining static.
- Why:
  - remote turns still needed more motion/readability even before true token interpolation lands
  - staggered path emphasis makes board movement read more like a route in progress rather than only a set of highlighted boxes
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 078

- Scope: P0-2 weather/fortune staging and prompt-surface simplification follow-up.
- Done:
  - Updated `apps/web/src/features/stage/TurnStagePanel.tsx` so live turns now expose a dedicated spotlight strip for:
    - weather
    - fortune
    - purchase
    - rent
  - Updated `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote-turn viewing now starts with a larger scene card instead of only small status cards.
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so:
    - movement prompt no longer uses the old context-card grid
    - movement choices now read more like a compact game HUD
    - roll detection no longer depends on a hardcoded Korean title check
  - Updated `apps/web/src/App.tsx` so the raw/debug toggle no longer sits in the always-visible top command row and only appears after opening the match-top panel.
  - Updated `apps/web/src/styles.css` to support the new spotlight / hero treatments and lighter top-command presentation.
  - Extended browser coverage in `apps/web/e2e/human_play_runtime.spec.ts` to lock:
    - `spectator-turn-scene`
    - `turn-stage-spotlight-strip`
    - hidden raw/debug toggle by default
- Why:
  - remote turns still felt too much like reading scattered panels instead of watching one live scene
  - movement prompt still carried inspector-like context-card structure
  - raw/debug controls were still too visible in the main match shell
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 079

- Scope: P0-1 canonical AI/human request-type mapping follow-up.
- Done:
  - Added `METHOD_REQUEST_TYPE_MAP` and `decision_request_type_for_method(...)` to `apps/server/src/services/decision_gateway.py`.
  - Updated `apps/server/src/services/runtime_service.py` so AI decision dispatch now uses the shared request-type resolver instead of a bridge-local mapping table.
  - Added regression coverage in `apps/server/tests/test_runtime_service.py` for canonical request-type resolution.
- Why:
  - the runtime bridge still owned one more string-heavy mapping that could drift away from the gateway contract
  - moving request-type normalization into the canonical decision module reduces future AI/human contract skew
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed (`10 passed, 13 skipped`)

### Entry 080

- Scope: P0-2 prompt-surface flattening follow-up.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so:
    - movement prompt now uses summary pills instead of the previous context-card block
    - mark target prompt now uses summary pills instead of the previous context-card block
    - purchase prompt now uses summary pills instead of the previous context-card block
    - lap reward prompt now uses summary pills instead of the previous context-card block
  - Kept the same gameplay data visible while reducing the "inspector card" look.
- Why:
  - even after the first prompt cleanup pass, major human-choice surfaces still looked too much like debugging cards
  - flattening those context areas preserves information while making the prompt feel closer to a board-game HUD
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

### Entry 081

- Scope: P0-2 board pawn-travel scene follow-up.
- Done:
  - Completed the in-flight board movement treatment in `apps/web/src/features/board/BoardPanel.tsx` by keeping the transient ghost pawn overlay wired to the latest move origin/destination coordinates.
  - Updated `apps/web/src/styles.css` so the board now renders a short-lived ghost pawn travel animation between move start and move end instead of relying on static badges alone.
  - Extended browser parity in `apps/web/e2e/human_play_runtime.spec.ts` to lock `board-moving-pawn-ghost`.
- Why:
  - recent path badges and tile pulses improved readability, but the board still lacked an obvious "piece moved here" moment
  - a lightweight ghost pawn animation adds scene continuity without needing full per-step interpolation yet
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed

### Entry 082

- Scope: P0-4 prompt locale-boundary cleanup follow-up.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so collapsed prompt chip text and footer request-meta text now come from locale resources instead of component-local string assembly.
  - Cleaned the English locale wording in `apps/web/src/i18n/locales/en.ts` for prompt collapse/meta lines so the default English mode no longer carries mojibake bullets in those surfaces.
  - Removed one leftover unused local helper after the locale-boundary handoff.
- Why:
  - prompt chrome still had a few direct user-facing literals inside the component, which breaks the bilingual/string-separation goal and makes encoding regressions easier to reintroduce
  - the user explicitly asked for clean KO/EN switching and stronger protection against string corruption
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed

### Entry 083

- Scope: P0-4 prompt choice-text locale cleanup extension.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so purchase-choice description text now also comes from locale resources instead of a component-local English fallback.
  - Normalized the English locale prompt wording in `apps/web/src/i18n/locales/en.ts` for:
    - collapsed chip
    - request meta
    - purchase choice description
- Why:
  - even after the first locale-boundary cleanup, purchase prompt wording still had one direct component-owned sentence
  - the default English mode still carried mojibake separators in a few prompt-facing strings
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/features/board/boardProjection.spec.ts src/domain/text/uiText.spec.ts` passed

### Entry 084

- Scope: P0-1 decision gateway lifecycle helper cleanup.
- Done:
  - Updated `apps/server/src/services/decision_gateway.py` so human and AI resolution paths now share internal helper methods for:
    - requested event publishing
    - resolved event publishing
    - timeout fallback event publishing
- Why:
  - even after canonical payload builders were introduced, the gateway still repeated nearly identical publish blocks in multiple branches
  - centralizing those publish paths lowers drift risk while continuing the "AI and human share one decision contract" track
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed

### Entry 085

- Scope: P0-2 remote-turn scene payoff and prompt simplification follow-up.
- Done:
  - Updated `apps/web/src/features/prompt/PromptOverlay.tsx` so the movement prompt now hides non-essential summary pills during normal dice mode and only surfaces selected-card state when the player is actually using dice cards.
  - Updated `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so spectator spotlight cards now use specific turn-stage labels (`purchase / rent / fortune / trick`) instead of generic `economy / effect` buckets, and the hero scene card now carries the latest public action headline together with the current beat summary.
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so:
    - tile purchase details now carry the acting player prefix
    - lap reward details now carry the acting player prefix
    - fortune draw / fortune resolution details now carry the acting player prefix
  - Re-stabilized `apps/web/src/i18n/locales/en.ts` after a broken legacy locale fragment in the board/weather fallback area was surfaced by build/e2e.
  - Normalized the English wording for:
    - tile purchase detail
    - rent detail
    - fortune draw / fortune resolution detail
    - movement prompt button text
- Why:
  - other-player turns still needed stronger "something just happened" payoff instead of flat status summaries
  - the movement prompt still exposed more bookkeeping than was useful during live play
  - build/e2e caught a legacy corrupted English locale fragment, so the string-stability track needed another hardening pass
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`2 passed`)

## 2026-04-06 Locale Restore Follow-up

- What changed:
  - Exported `resolveLocaleFromStoredValue(...)` from `apps/web/src/i18n/I18nProvider.tsx` so locale restore behavior is explicit and testable.
  - Fixed the restore path so both `ko` and `en` survive reloads instead of only recognizing stored English.
  - Replaced the broken legacy `apps/web/src/i18n/i18n.spec.ts` content with a clean UTF-8 spec that asserts English default plus bidirectional locale restore.
  - Extended `apps/web/e2e/human_play_runtime.spec.ts` so remote-turn continuity now also requires the spectator payoff card.
- Why:
  - the bilingual string architecture is not complete if locale switching silently resets after refresh
  - the human-play UI contract should protect the spectator payoff surface that was just added
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/i18n/i18n.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`32 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`3 passed`)

## 2026-04-06 Prompt / Spectator / Decision Drift Follow-up

- What changed:
  - Reordered `none` / pass-style options to the end of display order in mark and generic prompt surfaces so primary actions appear first.
  - Added a dedicated spectator journey strip that now reads remote turns as:
    - current character
    - current choice beat
    - movement
    - landing
    - economy/effect payoff
  - Added backend coverage that AI `mark_target` decisions also emit the canonical:
    - `decision_requested`
    - `decision_resolved`
    lifecycle with the `mark_target` request type.
- Why:
  - prompt surfaces were still front-loading passive choices and reading more like inspectors than live game choices
  - spectator continuity still needed one stronger scene-oriented strip in addition to spotlight/payoff cards
  - the unified decision plan needed one more specialty-method guard beyond purchase/movement paths
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py`

## 2026-04-06 Prompt Surface / Spectator Result / Active Flip Follow-up

- What changed:
  - Moved prompt request-meta out of the footer and into the header chrome so the bottom area stays focused on feedback and the timer bar.
  - Promoted character, mark, and generic choices onto the stronger emphasis card surface so prompts read less like inspector lists.
  - Added a dedicated spectator result card so remote purchase/rent/fortune outcomes stay visible as a distinct payoff beat.
  - Added backend coverage that AI `active_flip` decisions also stay on the canonical decision lifecycle.
- Why:
  - the previous prompt footer still felt too much like a tool panel
  - remote-turn payoff still benefited from one more persistent result card
  - specialty decision coverage should keep expanding before later `DecisionPort` migration
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py`

## 2026-04-06 Weather / Specialty Prompt / Specific Reward Follow-up

- What changed:
  - Added stronger remote-turn weather payoff visibility:
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx` now includes weather in the spectator spotlight strip
    - spectator journey now sequences purchase / rent / fortune as separate beats instead of collapsing them into one generic economy/effect bucket
    - `apps/web/src/features/stage/TurnStagePanel.tsx` now keeps weather in the scene strip and uses weather effect as an outcome beat when no fortune outcome is present
  - Split remaining specialty prompts out of the generic inspector path:
    - `active_flip`
    - `burden_exchange`
    - `specific_trick_reward`
    now render on their own card sections in `apps/web/src/features/prompt/PromptOverlay.tsx`
  - Added backend specialty-decision guard coverage for AI `choose_specific_trick_reward` so another non-trivial path stays on the canonical:
    - `decision_requested`
    - `decision_resolved`
    lifecycle.
  - Tightened browser parity so remote-turn spotlight/result assertions now match the new scene-style payoff wording.
- Why:
  - weather and payoff visibility still needed to feel like a continuing scene instead of disconnected status cards
  - a few remaining specialty prompts were still falling back to the generic choice grid and reading too much like tooling UI
  - unified decision coverage needed one more specialty seam guarded before later provider/port migration
- Validation:
  - `npm run build` passed (`apps/web`)
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts` passed (`29 passed`)
  - `npm run e2e -- e2e/human_play_runtime.spec.ts` passed (`3 passed`)
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` passed (`13 passed, 13 skipped`)

## 2026-04-06 Remaining Prompt Specialization / Doctrine-Burden Coverage

- What changed:
  - Split four remaining prompt families out of the generic fallback grid in `apps/web/src/features/prompt/PromptOverlay.tsx`:
    - `runaway_step_choice`
    - `coin_placement`
    - `doctrine_relief`
    - `geo_bonus`
  - Each now renders on the emphasized live-choice surface with summary pills/context instead of the plain generic inspector list.
  - Added weather as the first visible spectator journey beat in `apps/web/src/features/stage/SpectatorTurnPanel.tsx` so remote turns read more clearly as:
    - weather
    - character
    - current choice
    - movement
    - landing
    - payoff
  - Added backend canonical lifecycle coverage for AI:
    - `choose_doctrine_relief_target`
    - `choose_burden_exchange_on_supply`
- Why:
  - a few secondary human prompts were still falling back to the generic choice list and breaking the “game UI, not inspector UI” goal
  - spectator continuity still benefited from one stronger “weather starts the scene” beat
  - specialty decision drift needed to shrink further before later provider / `DecisionPort` migration
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` (`15 passed, 13 skipped`)

## 2026-04-06 Final Specialty Coverage / Payoff Animation Follow-up

- What changed:
  - Added backend canonical lifecycle coverage for the remaining specialty AI decisions:
    - `choose_runaway_slave_step`
    - `choose_coin_placement_tile`
    - `choose_geo_bonus`
  - Raised scene payoff one more step in `apps/web/src/styles.css` by adding a shared pulse animation to:
    - spectator payoff cards
    - spectator spotlight cards
    - turn-stage spotlight cards
    - turn-stage outcome cards
  - Result: purchase / rent / fortune outcomes now read more like active scene cards than flat status blocks.
- Why:
  - the unified decision boundary needed the remaining specialty seams covered before larger provider cleanup
  - human-play recovery still benefits from stronger event-card emphasis even before deeper animation/transition work
- Validation:
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` (`18 passed, 13 skipped`)
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-06 Human Pabal Dice Mode Recovery

- What changed:
  - Restored a missing human decision seam by implementing `choose_pabal_dice_mode(...)` in [GPT/viewer/human_policy.py](C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/viewer/human_policy.py).
  - Human seats now emit a real `pabal_dice_mode` prompt instead of silently falling through to the AI branch.
  - Added a dedicated `pabal_dice_mode` prompt surface in [apps/web/src/features/prompt/PromptOverlay.tsx](C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/apps/web/src/features/prompt/PromptOverlay.tsx).
  - Improved prompt choice parsing in [apps/web/src/domain/selectors/promptSelectors.ts](C:/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/apps/web/src/domain/selectors/promptSelectors.ts) so `value.description` is treated as a first-class fallback description source.
  - Added regression coverage for:
    - AI canonical lifecycle: `choose_pabal_dice_mode`
    - human prompt lifecycle: `choose_pabal_dice_mode`
    - prompt selector parsing of `value.description`
- Why:
  - this was a real human-play gap, not just a UI polish issue: the engine had a canonical request type, but the human bridge had no corresponding method
  - leaving it unfixed would have caused human seats to diverge from the unified decision contract exactly in a specialty ability branch
- Validation:
  - `npm run build`
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - `python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_stream_api.py` (`20 passed, 13 skipped`)

## 2026-04-06 Prompt HUD + Explicit Turn Event Labels

- What changed:
  - Reworked the prompt header in `apps/web/src/features/prompt/PromptOverlay.tsx` so the top meta now reads as compact HUD pills instead of a debug-style sentence.
  - Promoted explicit event naming in:
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx`
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
  - Purchase / rent / fortune reveal / fortune resolution / landing now use event-label wording where available, so the stage reads more like a live scene than a generic status board.
  - Updated `apps/web/src/styles.css` to style the new prompt-head HUD pills.
- Why:
  - the decision surface still carried a little too much inspector flavor
  - stage continuity became easier to read once payoff beats used explicit event names instead of generic field labels
- Validation:
  - pending local build/test pass after this patch

## 2026-04-06 Turn Handoff Scene Card

- What changed:
  - Added a dedicated end-of-turn handoff card to:
    - `apps/web/src/features/stage/SpectatorTurnPanel.tsx`
    - `apps/web/src/features/stage/TurnStagePanel.tsx`
  - Added matching styles in `apps/web/src/styles.css` so turn-end handoff now pulses as a closing beat instead of being buried in generic summaries.
  - Extended `apps/web/e2e/human_play_runtime.spec.ts` so the remote-turn browser regression now explicitly checks:
    - spectator handoff visibility
    - turn-stage handoff visibility
    - turn-end summary text
- Why:
  - live human play still needed a stronger visual handoff between one actor finishing and the next public phase beginning
  - this is a scene-continuity improvement, not just a text polish change
- Validation:
  - pending local build/test pass after this patch

## 2026-04-06 Payoff Persistence After Turn End

- What changed:
  - Updated `apps/web/src/features/theater/CoreActionPanel.tsx` so the result card now follows the latest payoff event in the same turn, not just the latest event overall.
  - This keeps purchase / rent / fortune payoff visible even when `turn_end_snapshot` becomes the newest public event.
- Why:
  - the previous UI dropped the payoff card as soon as turn-end arrived, which weakened scene continuity and broke the browser regression added for handoff.
- Validation:
  - pending local build/test pass after this patch

## 2026-04-06 Prompt Surface Coverage Lock

- What changed:
  - Added `apps/web/src/features/prompt/promptSurfaceCatalog.ts` as the canonical list of prompt types that must render on specialized UI surfaces.
  - Updated `PromptOverlay.tsx` so the generic fallback path now explicitly means "unknown request type" instead of silently covering known request types.
  - Added `apps/web/src/features/prompt/promptSurfaceCatalog.spec.ts` to assert that every `KNOWN_PROMPT_TYPES` entry is covered by a specialized prompt surface.
- Why:
  - this is a direct regression guard against the old problem where a known human choice path could quietly fall back to a generic inspector-like list
- Validation:
  - `cmd /c npm run build`
  - `cmd /c npm run test -- --run src/features/prompt/promptSurfaceCatalog.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `cmd /c npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-06 Plan / Status Documentation Cleanup

- What changed:
  - Reclassified recently finished slices versus active carry-forward work in:
    - `PLAN/PLAN_STATUS_INDEX.md`
    - `PLAN/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
  - Explicitly marked the following as closed for the current slice:
    - prompt specialization lock
    - `pabal_dice_mode` human seam repair
    - turn-handoff payoff continuity
  - Explicitly carried forward the next three active slices:
    - fortune / purchase / rent scene payoff
    - specialized prompt simplification
    - provider-local drift reduction before typed `DecisionPort` cleanup
- Why:
  - the execution documents had become append-heavy, making it harder to tell what was already done versus what should actually drive the next coding slice
- Validation:
  - documentation-only update

## 2026-04-07 Payoff Scene Strip + Local Validation Pass

- What changed:
  - Bootstrapped local validation dependencies for this workspace:
    - created `.venv/` and installed server-side Python test dependencies
    - installed `apps/web` npm dependencies and Playwright Chromium
  - Verified the current web runtime path end-to-end, then upgraded the theater payoff UI:
    - added `apps/web/src/features/theater/coreActionScene.ts`
    - added `apps/web/src/features/theater/coreActionScene.spec.ts`
    - updated `apps/web/src/features/theater/CoreActionPanel.tsx`
    - updated locale resources in `apps/web/src/i18n/locales/ko.ts` and `apps/web/src/i18n/locales/en.ts`
    - updated theater styling in `apps/web/src/styles.css`
  - The core-action payoff area now renders same-turn payoff beats in sequence instead of compressing them into a single latest result card:
    - `tile_purchased`
    - `rent_paid`
    - `fortune_drawn`
    - `fortune_resolved`
    - `lap_reward_chosen`
  - Classification now uses canonical `eventCode` first before fallback keyword heuristics, reducing inspector-like ambiguity in payoff rendering.
- Why:
  - the active carry-forward slice in the execution plans calls for stronger fortune / purchase / rent scene payoff, and the old UI still flattened those beats into one summary card
  - local runtime validation was also needed to distinguish real implementation issues from machine/environment issues
- Validation:
  - `npm run test -- --run src/features/theater/coreActionScene.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`
  - server-side note:
    - current local machine only exposes `python3` 3.9.6
    - `apps/server` currently imports `@dataclass(slots=True)` paths, so server import/test/runtime fail under 3.9 before app startup
    - `apps/server/tests/test_stream_api.py` also needs `httpx` in the local venv for FastAPI `TestClient`

## 2026-04-07 Python 3.11 Server Validation Recovery

- What changed:
  - Installed Homebrew `python@3.11` and created `.venv311/` for server validation.
  - Installed server dependencies plus `pytest` and `httpx` into `.venv311/`.
  - Re-ran the server validation batch with Python 3.11 and confirmed the FastAPI app binds successfully when sandbox port restrictions are lifted.
- Why:
  - the local machine defaulted to Python 3.9.6, which could not import the current server modules because `dataclass(slots=True)` requires Python 3.10+ in this codebase.
  - this was an environment blocker, not an app logic failure, so the execution path needed a valid interpreter before further server work.
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py` (`48 passed`)
  - `.venv311/bin/python -m uvicorn apps.server.src.app:app --host 127.0.0.1 --port 8001` (startup and bind confirmed)

## 2026-04-07 Prompt Head Locale Ownership Cleanup

- What changed:
  - Removed the remaining prompt-head meta pill string assembly from `apps/web/src/features/prompt/PromptOverlay.tsx`.
  - Added locale-owned `requestMetaPills` resources in:
    - `apps/web/src/i18n/locales/ko.ts`
    - `apps/web/src/i18n/locales/en.ts`
  - Extended `apps/web/src/i18n/i18n.spec.ts` to lock the Korean/English prompt-head pill output shape.
- Why:
  - prompt surface cleanup is still an active carry-forward slice, and the prompt head still had component-owned English literals even after the broader locale split work.
  - this keeps the prompt HUD aligned with the “locale resources outside components” rule and reduces inspector-style drift.
- Validation:
  - `npm run test -- --run src/i18n/i18n.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/features/theater/coreActionScene.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 PromptOverlay Specialized Surface Consolidation

- What changed:
  - Consolidated repeated emphasized-choice rendering in `apps/web/src/features/prompt/PromptOverlay.tsx` into shared local helpers:
    - `nonEmptyPills`
    - `choiceGridClass`
    - `EmphasisChoiceGrid`
  - Moved multiple specialized prompt surfaces onto the shared rendering path while preserving their existing test ids and context pills:
    - `purchase_tile`
    - `lap_reward`
    - `active_flip`
    - `burden_exchange`
    - `specific_trick_reward`
    - `runaway_step_choice`
    - `coin_placement`
    - `doctrine_relief`
    - `geo_bonus`
    - `pabal_dice_mode`
- Why:
  - this reduces repeated branch-local UI logic in the prompt layer and makes the remaining specialized prompts more consistent, which is directly aligned with the active prompt-surface simplification slice
  - it also makes follow-up prompt UX changes safer because layout behavior now flows through fewer duplicated blocks
- Validation:
  - `npm run test -- --run src/i18n/i18n.spec.ts src/domain/selectors/promptSelectors.spec.ts src/domain/selectors/streamSelectors.spec.ts src/domain/text/uiText.spec.ts src/features/board/boardProjection.spec.ts`
  - `npm run build`
  - `npm run e2e -- e2e/human_play_runtime.spec.ts`

## 2026-04-07 Decision Gateway Method Spec Registry

- What changed:
  - Replaced the repeated method-name branching in `apps/server/src/services/decision_gateway.py` with a shared `DecisionMethodSpec` registry.
  - The registry now owns, per decision method:
    - canonical `request_type`
    - AI `choice_id` serialization
    - specialized `public_context` enrichment
  - Kept the existing `decision_request_type_for_method`, `serialize_ai_choice_id`, and `build_public_context` interfaces intact so runtime callers did not need a wider migration.
  - Added `prepare_decision_method(...)` and switched `apps/server/src/services/runtime_service.py` to consume the prepared contract directly instead of pulling request type, context, and serializer through three separate helper calls.
  - Extended `apps/server/tests/test_runtime_service.py` with focused contract checks for:
    - `choose_purchase_tile`
    - `choose_specific_trick_reward`
    - `choose_runaway_slave_step`
- Why:
  - provider-local drift was still concentrated in three separate helper branches inside the decision gateway, which made it easy for a specialty decision to update one surface but miss the others
  - a shared method-spec registry reduces that drift without prematurely forcing the larger `DecisionPort` migration
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py apps/server/tests/test_prompt_service.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_contract_examples.py apps/server/tests/test_error_payload.py apps/server/tests/test_structured_log.py`

## 2026-04-07 Typed Provider Cleanup Follow-up

- What changed:
  - Split `_ServerDecisionPolicyBridge` dispatch responsibilities in `apps/server/src/services/runtime_service.py` across:
    - `_ServerHumanDecisionProvider`
    - `_ServerAiDecisionProvider`
  - Kept the bridge as the engine-facing adapter, but moved provider-specific execution behind explicit provider objects instead of concentrating human/AI logic in one branchy wrapper.
  - Added mixed-seat dispatch coverage in `apps/server/tests/test_runtime_service.py` to confirm:
    - human-seat prompt decisions do not fall through to the AI fallback provider
    - non-human seats still route through the AI provider even when a human provider is present
- Why:
  - this is the next smallest step in the plan's typed-provider cleanup track
  - it shrinks `_ServerDecisionPolicyBridge` toward provider selection and leaves provider-specific execution in narrower units ahead of a later `DecisionPort` migration
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Decision Provider Router Cleanup

- What changed:
  - Added `_ServerDecisionProviderRouter` in `apps/server/src/services/runtime_service.py` so the bridge no longer directly owns:
    - attribute target selection for engine policy access
    - seat-based provider selection for `choose_*` calls
  - Kept `__getattr__` only as the engine compatibility surface while moving its routing judgment into the dedicated router helper.
  - Added focused router tests in `apps/server/tests/test_runtime_service.py` covering:
    - human-policy attribute precedence
    - AI fallback attribute lookup
    - human-seat vs non-human-seat provider selection
- Why:
  - the engine still expects dynamic `choose_*` attributes, so `__getattr__` remains for now
  - moving the routing judgment out of the bridge keeps the remaining dynamic surface thinner and makes the eventual `DecisionPort` migration boundary easier to see
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Decision Invocation Prep Layer

- What changed:
  - Added `DecisionInvocation` plus `build_decision_invocation(...)` in `apps/server/src/services/decision_gateway.py`.
  - Updated runtime routing/provider execution so a normalized invocation object now carries:
    - `method_name`
    - raw `args` / `kwargs`
    - resolved `state`
    - resolved `player`
    - normalized `player_id`
  - Added `prepare_decision_method_from_invocation(...)` so provider execution no longer needs to re-thread raw method name and argument tuples through multiple helpers.
  - Extended `apps/server/tests/test_runtime_service.py` with focused invocation coverage.
- Why:
  - this is a small prep step toward a later engine-side `DecisionPort` migration
  - the engine still calls `choose_*`, but the server boundary now treats each decision as an explicit normalized invocation rather than a loose `(method_name, args, kwargs)` bundle
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Engine Decision Port Prep (Phase 1)

- What changed:
  - Added `DecisionRequest` and `DecisionPort` injection support to `GPT/engine.py`.
  - `GameEngine` now accepts an optional `decision_port=...` and otherwise wraps the legacy policy with the default port adapter.
  - Routed the PR-05 first-wave engine decision callsites through the injected port:
    - `choose_draft_card`
    - `choose_final_character`
    - `choose_movement`
    - `choose_trick_to_use`
    - `choose_purchase_tile`
  - Updated `GPT/effect_handlers.py` so landing purchase decisions also go through the engine decision port instead of calling policy methods directly.
  - Added `GPT/test_decision_port_contract.py` to verify those first-wave engine requests are emitted through the port.
- Why:
  - this creates the real engine-side injection seam promised by the plan without forcing the full `DecisionPort.request(...)` migration in one jump
  - the server/runtime cleanup from earlier is now matched by an engine boundary that can accept a future unified decision adapter
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`
  - note: `.venv311/bin/python -m pytest GPT/test_policy_hooks.py` still has an unrelated existing failure in `RuleScriptTests.test_default_rule_scripts_loaded` (`engine.rule_scripts.scripts == {}`), so it was not used as the gating pass for this slice

## 2026-04-07 Engine Decision Port Prep (Phase 2)

- What changed:
  - Routed the next engine decision slice through `GameEngine._request_decision(...)` as well:
    - `choose_mark_target`
    - `choose_lap_reward`
    - `choose_active_flip_card`
    - `choose_runaway_slave_step`
  - Extended `GPT/test_decision_port_contract.py` so the injected port now verifies both PR-05 and PR-06 style engine request emission.
- Why:
  - this keeps the engine migration moving in the plan's intended order without jumping straight to a fully rewritten `DecisionPort` API
  - with both the first and second decision waves routed through the port seam, the remaining work before later engine-side consolidation is much narrower
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`

## 2026-04-07 Engine Decision Port Prep (Phase 3)

- What changed:
  - Routed the remaining engine-side specialty decision callsites through `GameEngine._request_decision(...)`:
    - `choose_specific_trick_reward`
    - `choose_doctrine_relief_target`
    - `choose_burden_exchange_on_supply`
    - `choose_coin_placement_tile`
  - Expanded `GPT/test_decision_port_contract.py` so the injected port now verifies first-, second-, and third-wave engine decision requests.
  - `choose_geo_bonus` remains outside this wave because there is no direct engine/effect-handler callsite left to migrate in the current engine path.
- Why:
  - this completes the current engine-side callsite migration waves described before a later true `DecisionPort.request(...)` consolidation
  - at this point, the engine no longer directly calls the migrated `choose_*` methods from its core flow and instead relies on the injected request seam
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py GPT/test_draft_three_players.py GPT/test_event_effects.py`

## 2026-04-07 Canonical Decision Request Alignment

- What changed:
  - Added `CanonicalDecisionRequest` plus `build_canonical_decision_request(...)` in `apps/server/src/services/decision_gateway.py`.
  - Updated the server AI provider path to consume canonical request metadata before publishing decision lifecycle events.
  - Expanded `GPT/engine.py`'s injected `DecisionRequest` so it now carries canonical request-shaped metadata:
    - `request_type`
    - `player_id`
    - `round_index`
    - `turn_index`
    - `public_context`
    - `fallback_policy`
  - Added coverage on both sides:
    - `GPT/test_decision_port_contract.py`
    - `apps/server/tests/test_runtime_service.py`
- Why:
  - server `DecisionInvocation` and engine `DecisionRequest` were structurally close but still named and shaped differently in ways that would complicate the next real adapter step
  - aligning the metadata shape now makes the later engine-to-server decision adapter much more mechanical
- Validation:
  - `.venv311/bin/python -m pytest GPT/test_decision_port_contract.py`
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Server Engine Decision-Port Adapter Hookup

- What changed:
  - Added `build_decision_invocation_from_request(...)` in `apps/server/src/services/decision_gateway.py` so server routing can consume engine-style decision request objects directly.
  - `_ServerDecisionPolicyBridge` now implements `request(request)` and routes the normalized request through the existing provider router.
  - `RuntimeService._run_engine_sync(...)` now passes `decision_port=policy` when the server bridge is mounted, so the engine's injected port seam is actually exercised by the runtime path.
  - Expanded `apps/server/tests/test_runtime_service.py` to assert:
    - `GameEngine` receives the bridge as `decision_port`
    - engine-style request objects are routed through the bridge's AI provider path
- Why:
  - the previous steps aligned shapes but had not yet connected the engine injection seam to the live server runtime
  - this closes that gap and turns the engine `DecisionPort` preparation into an actually used server adapter path
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py`

## 2026-04-07 Frontend Canonical Prompt Contract Cleanup

- What changed:
  - Removed the web selector fallback to legacy prompt `choices` and now parse only canonical `legal_choices` in `apps/web/src/domain/selectors/promptSelectors.ts`.
  - Updated prompt selector coverage in `apps/web/src/domain/selectors/promptSelectors.spec.ts` so active/unresolved prompt cases also use canonical prompt payloads.
  - Simplified `apps/web/src/features/prompt/PromptOverlay.tsx` to prioritize the current prompt contract keys:
    - `tile_index`
    - `tile_zone`
    - `tile_purchase_cost`
    - `player_cash`
    - `player_shards`
    - `player_hand_coins`
    - `owned_tile_indices`
    - `actor_name`
  - Reduced old prompt-surface fallback usage so the React layer now follows the same canonical request/public-context shape that the server bridge and engine seam were aligned around.
- Why:
  - frontend prompt parsing still tolerated older payload names that are no longer the canonical runtime contract
  - removing those legacy branches makes the prompt surface easier to reason about and keeps the client aligned with the current server/human-policy envelope
- Validation:
  - `npm run test -- --run src/domain/selectors/promptSelectors.spec.ts`
  - `npm run build`
  - Updated `apps/web/src/domain/selectors/streamSelectors.ts` so turn-stage prompt focus uses canonical prompt data:
    - first `public_context.tile_index`
    - then `legal_choices[].value.tile_index`
  - Added `coin_placement` turn-stage coverage in `apps/web/src/domain/selectors/streamSelectors.spec.ts`.
  - `npm run test -- --run src/domain/selectors/streamSelectors.spec.ts`

## 2026-04-07 Open-Participant Decision Client Prep

- What changed:
  - Reframed runtime human/AI execution from provider-style branching toward decision-client adapters:
    - `_LocalHumanDecisionClient`
    - `_LocalAiDecisionClient`
    - `_ServerDecisionClientRouter`
    - `_ServerDecisionClientFactory`
  - The runtime router can now also resolve participant client type from session seat descriptors, not only from a bare `human_seats` list.
  - Added `RoutedDecisionCall` in `apps/server/src/services/decision_gateway.py` so both local clients consume the same normalized call object:
    - invocation
    - canonical request
    - choice serializer
  - Updated `_ServerDecisionPolicyBridge` so both `request(...)` and legacy `choose_*` wrappers route through the normalized decision-client seam.
  - Opened server-side DI one step further so client creation itself can be injected through a decision-client factory.
  - Extended `GPT/engine.py` with `decision_request_factory=...` injection so request construction is also open to adapters and not hard-wired to one server-local path.
  - Added coverage in:
    - `apps/server/tests/test_runtime_service.py`
    - `GPT/test_decision_port_contract.py`
- Why:
  - the next architectural target is not merely “AI and human use similar contracts”, but “AI can be treated like the same kind of multiplayer participant”
  - local AI still exists today, but it should already look like a client adapter at the server boundary so a later external AI client can mount on the same seam
  - opening request construction DI on the engine side keeps the engine boundary compatible with multiple participant adapters instead of only the current default builder
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_runtime_service.py GPT/test_decision_port_contract.py`

## 2026-04-07 External AI Participant Descriptor Hookup

- What changed:
  - Extended `SeatConfig` with participant-level client metadata:
    - `participant_client`
    - `participant_config`
  - `SessionService` now validates and persists participant descriptors for seats:
    - human seats default to `human_http`
    - AI seats default to `local_ai`
    - AI seats can now explicitly declare `external_ai`
  - Session HTTP payloads now expose participant descriptors in create/public/start responses.
  - Runtime client selection now uses seat-level participant descriptors:
    - local AI seats route to the local AI decision client
    - `external_ai` seats route to an `_ExternalAiDecisionClientPlaceholder`
  - The external AI placeholder still resolves through the local gateway today, but it preserves:
    - explicit participant boundary
    - seat-specific config
    - a dedicated upgrade seam for future real external workers/services
- Why:
  - the architecture goal is no longer just “AI and humans share similar decision events”; it is “AI can participate through the same kind of open multiplayer boundary”
  - seat descriptors are the smallest stable way to carry that participant intent from session creation through runtime routing
- Validation:
  - `.venv311/bin/python -m pytest apps/server/tests/test_session_service.py apps/server/tests/test_runtime_service.py apps/server/tests/test_sessions_api.py`
