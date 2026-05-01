# [REPORT] Redis UI Playtest Findings

Status: ACTIVE_FINDINGS
Date: 2026-04-30
Method: Local Redis runtime + FastAPI + Vite web app + in-app browser visual playtest
Session: `sess_chv3RQH_lrU0LEPDw1MA_E4U`
Retest session: `sess_NMsoo39MjWt2xJQnP1Y9HSP5`
Live verification session: `sess_i_4YOXJeO4L-sO_Znf8fnJ1_`

## Purpose

Document the concrete issues found while validating the Redis-based migration through the actual game screen.

This report is evidence from a real UI path, not a static code review. It should be used before declaring the Redis gameplay migration complete.

## Runtime Under Test

- Redis: `redis://127.0.0.1:6379/0`
- Redis key prefix: `mrn:ui-playtest:1777543483`
- Backend: `http://127.0.0.1:9090`
- Web app: `http://127.0.0.1:9000`
- Browser route: `/#/match`
- Session mode: lobby quick start, human P1 plus AI seats

Health check confirmed the backend was using Redis for live storage:

```json
{
  "storage": {
    "sessions": "redis",
    "rooms": "redis",
    "streams": "redis"
  },
  "redis": {
    "configured": true,
    "ok": true,
    "version": "7.4.8",
    "key_prefix": "mrn:ui-playtest:1777543483",
    "database": 0
  }
}
```

## What Passed

- Lobby rendered successfully in the browser.
- `Quick start with 3 AI` created a match and navigated to `/#/match`.
- Board, player strip, weather card, and decision panel rendered without a blank-screen failure.
- Browser console warnings/errors were empty during the captured screens.
- Character draft prompt rendered and accepted the P1 draft choice.
- Redis replay and runtime APIs returned coherent session data when called with the player token.
- The local fast-check rule harness still passed:

```text
Test Files  4 passed (4)
Tests       12 passed (12)
```

Covered specs:

- `apps/web/src/domain/rules/engineCore.rules.spec.ts`
- `apps/web/src/features/board/boardProjection.rules.spec.ts`
- `apps/web/src/domain/characters/prioritySlots.rules.spec.ts`
- `apps/web/src/test/harness/gameRuleHarness.spec.ts`

## Findings

### REDIS-UI-01 - P1 trick skip loops instead of advancing to movement

Severity: P0

After P1 completed character draft, the UI moved to `Decision: Use Trick`. Choosing `Do not use a trick` was accepted by the backend, but the game did not advance into movement or landing resolution.

Instead, each manual wakeup produced another turn start and another `trick_to_use` prompt.

Observed replay summary:

```json
{
  "event_count": 29,
  "turn_starts": 3,
  "trick_prompts": 3,
  "movement_events": 0
}
```

Observed event pattern:

```text
turn_start
trick_window_open
prompt_requested trick_to_use:2
decision_ack accepted
turn_start
trick_window_open
prompt_requested trick_to_use:3
decision_ack accepted
turn_start
trick_window_open
prompt_requested trick_to_use:4
```

Expected behavior:

- declining trick use should close the trick window for that turn
- the runtime should proceed to the next legal turn phase, usually movement or the next queued decision
- repeated `trick_to_use` prompts for the same player should not be emitted without an intervening rule-state change

Initial investigation targets:

- `GPT/engine.py`
- `apps/server/src/services/decision_gateway.py`
- `apps/server/src/services/runtime_service.py`
- `apps/server/src/workers/command_wakeup_worker_app.py`

Fix note, 2026-04-30:

- Root cause: Redis transition replay hydrates a checkpoint from immediately before the pending human prompt. The runtime seeded the bridge with the already-emitted `prompt_sequence`, so the replay minted `trick_to_use:3` instead of rebuilding the accepted `trick_to_use:2` request id. Because stable request ids include `prompt_instance_id`, the accepted skip decision was not replayed and the engine restarted the same turn phase.
- Fix: `RuntimeService` now seeds prompt sequence to `pending_prompt_instance_id - 1` when a checkpoint has `pending_prompt_request_id`, allowing the first prompt during replay to reconstruct the same stable request id and consume the accepted response. The next prompt then advances normally.
- Regression: `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_pending_prompt_replay_reuses_stable_request_id_then_advances_sequence` covers replaying the accepted trick skip and advancing to the next prompt id.
- Lesson: prompt ids in Redis transition replay are part of the continuation contract, not only UI correlation metadata. A resumed transition must deterministically regenerate the pending prompt id before it can safely advance.
- Status: partially improved in code and covered by runtime-service tests, but the 2026-04-30 browser retest below found a remaining live Redis flow blocker after movement confirmation.

### REDIS-UI-02 - Runtime status polling omits the session token

Severity: P1

The match screen repeatedly called:

```text
GET /api/v1/sessions/{session_id}/runtime-status
```

without the player session token. The backend correctly rejected this with `401 SPECTATOR_NOT_ALLOWED`, because private runtime status is not spectator-safe.

The UI ignored the error, so the visible screen did not crash, but the server logs were noisy and the browser could not use authenticated runtime status for recovery.

Observed backend error:

```json
{
  "ok": false,
  "error": {
    "code": "SPECTATOR_NOT_ALLOWED"
  }
}
```

Relevant frontend code:

- `apps/web/src/infra/http/sessionApi.ts`
- `apps/web/src/App.tsx`

Expected behavior:

- runtime-status reads from an authenticated player view should include the session token
- spectator-safe runtime status should be a separate contract if the UI needs unauthenticated polling
- polling failures should be visible in diagnostics instead of silently looping forever

Fix note, 2026-04-30:

- Root cause: the web HTTP helper only accepted `sessionId`, so `App.tsx` could not attach the active player session token to runtime-status polling. The polling effect also did not depend on `token`, so restoring or joining as a player did not refresh the request with authenticated state.
- Fix: `getRuntimeStatus(sessionId, token)` now appends `?token=...` when a token is available, and the match-screen polling effect passes `token` and reruns when it changes.
- Validation: `npm --prefix apps/web run build`.
- Lesson: browser polling helpers for viewer-scoped APIs should accept the viewer credential at the API boundary, even when the returned payload is redacted/public-safe.
- Status: fixed in code and confirmed in the 2026-04-30 browser retest when the web app used the player token. Manual unauthenticated curl calls still correctly return `401 SPECTATOR_NOT_ALLOWED`.

### REDIS-UI-03 - Background command wakeup did not visibly resume the accepted UI decisions

Severity: P1

The command wakeup worker and prompt timeout worker were running with the same Redis key prefix as the backend. However, after UI decisions were accepted, the session did not visibly advance until a manual one-shot wakeup was run:

```bash
MRN_REDIS_URL=redis://127.0.0.1:6379/0 \
MRN_REDIS_KEY_PREFIX="$(cat /tmp/mrn-ui-playtest-prefix.txt)" \
MRN_GAME_LOG_ARCHIVE_PATH=/tmp/mrn-ui-playtest-game-logs \
.venv/bin/python -m apps.server.src.workers.command_wakeup_worker_app \
  --once \
  --session-id sess_chv3RQH_lrU0LEPDw1MA_E4U
```

The one-shot wakeup reported `wakeup_count=1` and emitted the next prompt, which proves the Redis command path was not dead. The issue is likely in worker wakeup cadence, lease/visibility of pending commands, or the interaction between the accepted command and runtime waiting state.

Expected behavior:

- accepted UI decisions should be consumed by the background worker without manual intervention
- if a worker intentionally polls on a longer interval, the UI should still show a clear waiting state and recover without repeated manual wakeups

Initial investigation targets:

- `apps/server/src/workers/command_wakeup_worker_app.py`
- `apps/server/src/services/runtime_service.py`
- Redis command stream / runtime lease keys for the session

### REDIS-UI-04 - Movement confirmation reopens trick prompt instead of resolving movement

Severity: P0

Retest date: 2026-04-30
Retest session: `sess_NMsoo39MjWt2xJQnP1Y9HSP5`
Redis key prefix: `mrn:ui-retest:1777546713`

After the initial fix, the original `trick_to_use:1` repeated-prompt loop no longer reproduced in the same exact form. With a manual one-shot wakeup, the accepted trick skip advanced to the `movement` prompt and the UI rendered `선택 요청: 이동값 결정`.

However, confirming movement still did not produce movement or landing events. The UI accepted the movement decision, then remained in a waiting state until another manual one-shot wakeup was run. That wakeup reopened a new `trick_to_use:2` prompt for the same P1 turn instead of resolving movement.

Observed event tail after `굴리기 확정`:

```json
{
  "event_count": 26,
  "movement_prompt_requests": 1,
  "movement_acks": 1,
  "movement_events": 0,
  "tail": [
    {
      "seq": 23,
      "type": "prompt",
      "request_type": "movement",
      "request_id": "sess_NMsoo39MjWt2xJQnP1Y9HSP5:r1:t1:p1:movement:2"
    },
    {
      "seq": 25,
      "type": "event",
      "event": "prompt_required",
      "request_type": "movement",
      "status": "waiting_input"
    },
    {
      "seq": 26,
      "type": "decision_ack",
      "status": "accepted",
      "request_id": "sess_NMsoo39MjWt2xJQnP1Y9HSP5:r1:t1:p1:movement:2"
    }
  ]
}
```

Observed event tail after a manual one-shot wakeup following the movement ack:

```json
{
  "event_count": 31,
  "movement_events": 0,
  "tail": [
    {
      "seq": 27,
      "type": "event",
      "event": "turn_start"
    },
    {
      "seq": 28,
      "type": "event",
      "event": "trick_window_open"
    },
    {
      "seq": 29,
      "type": "prompt",
      "request_type": "trick_to_use",
      "request_id": "sess_NMsoo39MjWt2xJQnP1Y9HSP5:r1:t1:p1:trick_to_use:2"
    },
    {
      "seq": 31,
      "type": "event",
      "event": "prompt_required",
      "request_type": "trick_to_use",
      "status": "waiting_input"
    }
  ]
}
```

Expected behavior:

- confirming movement should consume `movement:2`
- the engine should emit dice/movement/landing resolution events, such as `dice_roll`, `player_move`, landing/purchase/toll prompts, or the next legal phase
- the same P1 turn should not restart at `trick_window_open` after a movement decision has been accepted

Evidence captured:

- `mrn-retest-movement-prompt.png`: movement prompt rendered after manual wakeup
- `mrn-retest-trick-loop-after-movement.png`: new trick prompt rendered after movement ack plus manual wakeup

Initial investigation targets:

- `apps/server/src/services/runtime_service.py`
- `apps/server/src/services/decision_gateway.py`
- `GPT/engine.py`
- `apps/server/src/workers/command_wakeup_worker_app.py`
- Redis runtime checkpoint fields around `pending_prompt_request_id`, `pending_prompt_instance_id`, and checkpoint position after accepted `movement`

Fix note (2026-04-30):

- Root cause:
  - `GPT/engine.py::_take_turn` deterministically asks the same-turn trick prompt before the movement prompt.
  - Redis checkpoint replay seeded prompt sequence as if the pending prompt itself were the first prompt to replay.
  - For a pending `movement:2`, that produced a new `trick_to_use:2` instead of replaying and consuming the already accepted `trick_to_use:1` before reaching `movement:2`.
  - `PromptService.wait_for_decision()` also popped accepted decisions on first read, so a later replay could not read the same accepted trick decision again.
- Code changes:
  - `RuntimeService._prompt_sequence_seed_for_transition()` now backs up to the deterministic replay prefix for movement prompts.
  - `PromptService` now keeps accepted decisions readable until the resolved-prompt TTL expires, while still deleting timed-out decisions.
  - `RedisPromptStore` exposes non-destructive `get_decision()` for replay; destructive `pop_decision()` remains available for tests and explicit cleanup.
- Regression coverage:
  - `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_pending_movement_replay_replays_prior_trick_prompt_before_movement`
  - `apps/server/tests/test_prompt_service.py::PromptServiceTests::test_wait_for_decision_returns_submitted_payload`
  - `apps/server/tests/test_redis_realtime_services.py::RedisRealtimeServicesTests::test_prompt_service_uses_redis_store_for_decision_flow`
- Status:
  - Code-level fix is in place.
  - A live Redis browser retest is still required before closing the release gate.

### REDIS-UI-05 - Accepted decisions still require manual one-shot wakeups in live browser play

Severity: P0

Retest date: 2026-04-30

The command wakeup worker and prompt timeout worker were running with the same Redis prefix as the backend, but accepted UI decisions did not advance the runtime on their own during the browser retest.

Observed behavior:

- P1 draft choice was accepted, but the UI stayed in waiting state until manual `command_wakeup_worker_app --once --session-id ...`.
- P1 trick skip was accepted, but the UI stayed in waiting state until another manual one-shot wakeup.
- P1 movement confirmation was accepted, but the UI again stayed in waiting state until manual wakeup.

The manual wakeups all reported `wakeup_count=1`, so the command path was recoverable. The failure is that the continuously running background worker did not consume the accepted commands in time for live gameplay.

Expected behavior:

- accepted UI decisions should be consumed by the background worker without manual intervention
- browser play should progress through draft, trick, movement, and landing using the normal worker runtime only

Current status:

- Code-level fix is in place; live Redis browser retest is still required.
- This finding supersedes the weaker wording in `REDIS-UI-03`; manual wakeup dependence was confirmed across draft, trick, and movement prompts.

Fix note (2026-04-30):

- Root cause:
  - The long-lived command wakeup worker discovered active sessions from its `SessionService` in-memory cache.
  - In Redis mode, sessions created after worker startup were persisted to Redis but were not visible to that already-started cache.
  - Manual `--session-id` wakeups bypassed active-session discovery, which is why every manual one-shot recovered with `wakeup_count=1`.
  - Standalone worker entrypoints also inherited the default server recovery policy unless explicitly configured; workers are not the session owner and should not abort in-progress sessions during import-time recovery.
- Code changes:
  - `SessionService.refresh_from_store()` reloads session payloads from the shared session store.
  - `CommandStreamWakeupWorker` refreshes sessions before scanning and before processing a command.
  - `command_wakeup_worker_app` and `prompt_timeout_worker_app` default `MRN_RESTART_RECOVERY_POLICY` to `keep` before importing shared state.
  - `docker-compose.yml` sets `MRN_RESTART_RECOVERY_POLICY=keep` for both standalone workers.
- Regression coverage:
  - `apps/server/tests/test_command_wakeup_worker.py::CommandStreamWakeupWorkerTests::test_wakeup_worker_refreshes_redis_sessions_created_after_start`
- Lesson:
  - Long-lived Redis worker processes must treat shared Redis stores as the source of truth before each active-session scan.
  - Server recovery policy and worker recovery policy are separate contracts; worker roles should not run a startup policy that can abort sessions.

### REDIS-UI-06 - Command wakeup consumed the decision but left queued runtime actions idle

Severity: P0

Live retest date: 2026-04-30
Live retest session: `sess_i_4YOXJeO4L-sO_Znf8fnJ1_`
Redis key prefix: `mrn:ui-live:1777548299`

After the REDIS-UI-04 and REDIS-UI-05 fixes, the browser could click through draft, trick skip, and movement without manual one-shot wakeups. The first live retest still found one deeper runtime bug: confirming movement emitted `dice_roll`, but the runtime stopped with one queued pending action and no `player_move` or landing resolution.

Observed failing signal from the live Redis session before this fix:

```json
{
  "last_event": "engine_transition",
  "pending_actions": 1,
  "runtime_status": "idle",
  "emitted": ["dice_roll"],
  "missing": ["player_move", "landing_resolved"]
}
```

Expected behavior:

- a consumed movement decision should resume the runtime until the next blocking human prompt, the end of the game, or an unavailable runtime
- internal queued actions such as `apply_move`, landing resolution, and purchase prompt setup should not require a second human command to wake the runtime
- the command stream offset should still be recorded exactly once for the accepted decision command

Root cause:

- `RuntimeService.process_command_once()` called a single `_run_engine_transition_once_sync(...)`.
- That consumed and acknowledged the accepted movement command, then committed only the first engine step (`dice_roll`).
- The committed checkpoint still had queued pending actions, but no new command existed to wake the worker again, so the session became idle with unfinished runtime work.

Code changes:

- `process_command_once()` now uses `_run_engine_transition_loop_sync(...)` for command-driven wakeups.
- The first loop iteration records the command consumer/sequence metadata, while later internal transitions run without command metadata.
- The loop continues until the runtime reaches `waiting_input`, `finished`, or `unavailable`.

Regression coverage:

- `apps/server/tests/test_runtime_service.py::RuntimeServiceTests::test_process_command_once_continues_after_command_transition_until_prompt`

Lesson:

- A Redis command is a wakeup edge, not a single engine-step budget.
- Command stream offsets and engine transition draining are separate contracts: record the accepted decision once, then drain deterministic queued actions until the next external input boundary.

## 2026-04-30 Retest Summary

Runtime under retest:

```json
{
  "storage": {
    "sessions": "redis",
    "rooms": "redis",
    "streams": "redis"
  },
  "redis": {
    "configured": true,
    "ok": true,
    "version": "7.4.8",
    "key_prefix": "mrn:ui-retest:1777546713",
    "database": 0
  }
}
```

Retest pass signals:

- Lobby, match board, draft prompt, trick prompt, and movement prompt rendered in the in-app browser.
- Browser console had `0` errors and `0` warnings.
- Authenticated `runtime-status?token=...` calls returned `200`.
- The previous exact repeated `trick_to_use:1` loop improved: accepted trick skip advanced to `movement` after manual wakeup.
- Rule harness still passed:

```text
Test Files  4 passed (4)
Tests       12 passed (12)
```

Retest failing signals:

- Background worker did not automatically consume accepted UI decisions in the captured retest.
- Movement confirmation produced `decision_ack accepted` but no movement or landing events in the captured retest.
- Manual wakeup after accepted movement reopened `trick_to_use:2` instead of resolving movement in the captured retest.
- Code-level fixes now cover these paths, but the Redis gameplay migration still needs a fresh browser retest that completes a real turn.

## 2026-04-30 Live Verification Summary

Runtime under live verification:

```json
{
  "storage": {
    "sessions": "redis",
    "rooms": "redis",
    "streams": "redis"
  },
  "redis": {
    "configured": true,
    "ok": true,
    "version": "7.4.8",
    "key_prefix": "mrn:ui-live:1777548299",
    "database": 0
  }
}
```

Verified browser path:

1. Quick start from the lobby.
2. P1 character draft choice.
3. P1 trick prompt skip.
4. P1 movement confirmation.
5. Purchase prompt after landing.
6. Purchase decline.

Live pass signals:

- The browser UI reached the `movement` prompt through the normal background worker path.
- Confirming movement emitted `dice_roll`, `player_move`, `landing_resolved`, and `purchase_tile`.
- Declining purchase removed the P1 prompt, ended P1's turn, processed AI turns, and returned to P1 with the next `draft_card` prompt in round 2.
- Runtime status ended at `waiting_input`, not `idle`, with the pending round-2 draft prompt.
- Command stream offset advanced through accepted P1 decisions and did not require manual `--once` wakeups.

Observed live event chain:

```text
decision_resolved trick_to_use
decision_resolved movement
dice_roll
player_move 0 -> 22
landing_resolved
decision_requested purchase_tile
decision_resolved purchase_tile
turn_end_snapshot
ai_decision / dice_roll / player_move / landing_resolved ...
round_start round=2
decision_requested draft_card
```

Captured evidence:

- `/tmp/mrn-ui-live-play-fixed.png`: movement resolved to a purchase prompt after landing.
- `/tmp/mrn-ui-live-play-after-purchase.png`: purchase prompt cleared and play advanced through AI turns to P1 round 2.

## Reproduction

1. Start Redis on `127.0.0.1:6379`.
2. Start the backend with Redis enabled:

```bash
MRN_REDIS_URL=redis://127.0.0.1:6379/0 \
MRN_REDIS_KEY_PREFIX=mrn:ui-playtest:<unique-id> \
MRN_GAME_LOG_ARCHIVE_PATH=/tmp/mrn-ui-playtest-game-logs \
.venv/bin/uvicorn apps.server.src.app:app --host 127.0.0.1 --port 9090
```

3. Start the command wakeup and prompt timeout workers with the same Redis prefix.
4. Start the web app:

```bash
MRN_WEB_API_TARGET=http://127.0.0.1:9090 \
npm run dev -- --host 127.0.0.1 --port 9000
```

5. Open `http://127.0.0.1:9000/`.
6. Click `Quick start with 3 AI`.
7. Choose a P1 draft character.
8. On `Decision: Use Trick`, click `Do not use a trick`.
9. Observe that the decision is accepted and the movement prompt appears through the background worker.
10. Click `굴리기 확정` on `선택 요청: 이동값 결정`.
11. Observe that `dice_roll`, `player_move`, and `landing_resolved` are emitted before the next blocking prompt.
12. If the session becomes `idle` with `pending_actions > 0`, inspect REDIS-UI-06 first.

## Release Gate

Do not consider Redis gameplay migration complete until every item has a current live verification signal:

1. `Do not use a trick` advances exactly once to the next legal phase. Current live verification: passed on `sess_i_4YOXJeO4L-sO_Znf8fnJ1_`.
2. At least one real browser playtest reaches movement and landing resolution through the Redis runtime. Current live verification: passed with `dice_roll`, `player_move`, `landing_resolved`, and `purchase_tile`.
3. Runtime status polling uses the correct viewer token or a deliberately public status endpoint. Current live verification: authenticated polling returned successfully during browser play.
4. Background workers consume accepted UI decisions without manual one-shot wakeups. Current live verification: passed through draft, trick, movement, purchase, AI turns, and round-2 draft.
5. The fast-check harness includes an integration-level property or scripted harness case that fails on repeated same-phase prompt loops.
6. Movement confirmation emits movement and landing events before any new same-turn trick prompt can open. Current live verification: passed on `sess_i_4YOXJeO4L-sO_Znf8fnJ1_`.

### 2026-05-01 Known-Issue Closure

The follow-up 4-human browser playtest found two backend ownership bugs and one screen-visibility gap:

- Redis-backed public reads could use stale process-local session/runtime memory after archive cleanup removed Redis hot keys.
- Backend `view_state.reveals` omitted high-signal public effects such as `trick_used`, `lap_reward_chosen`, and `game_end`, so the frontend could miss overlays even when the stream contained the rule event.
- Lap reward wording did not say the 10-point reward budget must be spent exactly.

Fixes landed with regression coverage in:

- `apps/server/tests/test_session_service.py`
- `apps/server/tests/test_runtime_service.py`
- `apps/server/tests/test_view_state_reveal_selector.py`
- `apps/web/src/domain/selectors/streamSelectors.spec.ts`

Root-cause lessons were distilled into `docs/engineering/[LESSONS]_REDIS_RUNTIME_UI_PLAYTEST.md`.

### 2026-05-01 REDIS-UI-07 Closure: Stale Trick Prompt Before Tile Target

Updated report from live play: after selecting a character and using `긴장감 조성`, the UI could appear to jump back to an old selection surface before returning to the 잔꾀 target screen.

Root cause:

- The engine correctly used the card and queued `resolve_trick_tile_rent_modifier`.
- The prompt lifecycle projection did not close the old `trick_to_use` prompt when the same-player `trick_used` event arrived.
- If the follow-up `trick_tile_target` prompt had not arrived/rendered yet, the frontend fallback selector could resurrect the stale prompt, making a valid queued-action transition look like a rollback.

Fix:

- Backend `view_state.prompt` and frontend fallback prompt selectors now close same-player `trick_to_use` prompts on `trick_used` and `trick_window_closed`.
- Regression tests cover the stale prompt close rule in both selector layers, plus a browser click path that uses `긴장감 조성` and waits for the queued tile-target prompt.

Validation:

- `npm --prefix apps/web run test -- src/domain/selectors/promptSelectors.spec.ts`
- `npm --prefix apps/web run e2e -- parity.spec.ts -g "trick use advances"`
- `.venv/bin/python -m pytest apps/server/tests/test_view_state_prompt_selector.py -q`

### 2026-05-01 REDIS-UI-08 Closure: Queued Trick Movement Reopened Trick Prompt

Updated report from play: after using `극심한 분리불안`, the game could ask the same player to use a trick again.

Root cause:

- The priority action queue correctly ran the trick-generated movement path, starting with `apply_move` and then `resolve_arrival`.
- The trick phase returned early because it had queued work, but it did not append `continue_after_trick_phase` behind that queued work.
- After movement and arrival drained the queue, `turn_index` still pointed to the same player with no pending turn completion. The next transition therefore entered turn start again and could produce a second `trick_to_use` prompt if another trick remained in hand.

Fix:

- `GameEngine._use_trick_phase()` now records whether applying a trick added pending actions. When it did, and the turn has a continuation payload, it appends `continue_after_trick_phase` after the trick-generated actions.
- The continuation is marked as already hidden-trick-synced because the hand visibility sync has already happened before appending it.

Validation:

- `.venv/bin/python -m pytest GPT/test_rule_fixes.py -k 'queued_trick_action_resumes_after_effect_without_second_trick_prompt or hidden_trick_prompt_resumes_after_applied_trick' -q`
- `.venv/bin/python -m pytest GPT/test_engine_resumable_checkpoint.py -k 'extreme_separation' -q`
- `npm --prefix apps/web run e2e -- parity.spec.ts -g "extreme separation"`
- `npm --prefix apps/web run e2e -- parity.spec.ts -g "trick use advances"`

### 2026-05-01 REDIS-UI-09 Closure: Draft Order, Turn Order, And Mark Target Projection Drift

Updated report from play: targeting, draft display, and turn order all looked wrong after character selection and trick use.

Root cause:

- The engine's priority queue was not the only thing that defines the visible order. The UI also consumes `view_state.players.ordered_player_ids`, raw `round_order`, session seats, and mark-target prompt metadata.
- Backend `view_state.players.ordered_player_ids` kept projecting marker/draft order even after a later `round_order` event had established the real turn order.
- The frontend raw-event fallback made the same mistake: it could keep using marker/draft order when backend projection was absent.
- `App.tsx` computed marker/turn-ordered players, but the player strip then ignored that list and sorted session seats by seat number.
- `PromptOverlay` filtered mark-target choices down to candidates and accidentally dropped the explicit `none` / "지목 안 함" choice.

Fix:

- Backend player projection now prefers the latest live `round_order` after draft has completed, while preserving marker owner and draft direction metadata.
- Frontend fallback player ordering now also prefers `snapshot.currentRoundOrder` before marker/draft ordering.
- The match player strip now ranks session seats by projected player order instead of always falling back to seat order.
- Mark-target rendering preserves the explicit no-target choice after candidate ordering.

Validation:

- `.venv/bin/python -m pytest apps/server/tests/test_view_state_player_selector.py -q`
- `npm --prefix apps/web run test -- src/domain/selectors/streamSelectors.spec.ts --run`
- `npm --prefix apps/web run e2e -- --project=chromium --grep "purchase and mark prompts render dedicated decision cards"`

### 2026-05-01 REDIS-UI-10 Resolved: Effect And Spectator Context Regression In Human Runtime E2E

Status: RESOLVED
Severity: P1
Retest method: Docker Redis runtime, `npm run e2e:human-runtime`, and one live `1 human + 3 AI` browser session.
Live session: `sess_KGL_loUo4XDdTa1U-VX3prLN`
Browser URL: `http://127.0.0.1:9000/#/match?session=sess_KGL_loUo4XDdTa1U-VX3prLN&token=session_p1_G2hGsQPTefhSOTraap25-A`

Resolution update, 2026-05-01:

- Restored the non-prompt spectator continuity surface in the match overlay and kept the previous `core-action-*` DOM contract available for browser verification.
- Added addressable reveal markers for spotlighted latest public events so `board-event-reveal-*` remains provable even when the newest reveal is promoted out of the history list.
- Reordered spectator and core-action sequences by cause/effect priority instead of raw insertion time, so worker fallback, marker/flip, and fortune resolution remain first-class readable causes.
- Capped desktop character/draft prompt width and removed the desktop card minimum-height overflow that made blocking prompts scroll the document.
- Restored projected economy text shadow for weather/economy readability.

Resolution validation:

```text
npm --prefix apps/web run build
npm --prefix apps/web run e2e:human-runtime
18 passed

cd apps/web
npm exec -- playwright test e2e/parity.spec.ts --project=chromium --workers=1 --grep "trick use advances to tile target without resurrecting the stale trick picker|extreme separation trick closes picker while queued movement resolves"
2 passed
```

Runtime health:

- Docker services started with Redis-backed storage.
- `/health` returned `sessions=redis`, `rooms=redis`, `streams=redis`, Redis `7.4.8`, key prefix `mrn:dev`.
- Web app responded on `http://127.0.0.1:9000`.
- Test environment was cleaned up with `./run-docker.sh down` after the run.

What passed in the live browser session:

- The browser did not hit the previous React crash (`Should not already be working`).
- Console errors, page errors, and failed network requests were empty.
- The screen rendered 4 player cards and 40 board tiles throughout the sampled run.
- Weather context was visible as a current round panel.
- Human prompts advanced through draft, trick pass, movement, purchase decline, a second draft/trick/movement cycle, and a `burden_exchange` prompt.
- Redis replay contained 150 stream entries, so the runtime was actively progressing rather than failing at boot.

Pre-fix live-browser gaps:

- Event-feed controls were not discoverable by the test harness in the sampled DOM (`eventToggle: 0` at initial load, `eventReveals: 0` after attempted open).
- `spectator-turn-panel` / `stage-flow-panel` were not present in the final sampled DOM, even while the user-facing screen showed a broad decision/stage bar.
- The final screen was readable but did not expose a durable, test-addressable reveal stack for causal effects.

Pre-fix human runtime e2e result:

```text
npm run e2e:human-runtime
18 tests total
9 passed
9 failed
```

Pre-fix passed coverage:

- quick-start first prompt and turn banner
- local my-turn panel layout
- remote-turn waiting continuity without local prompt
- fortune cash-loss overlay/feed readability
- innkeeper lap-bonus breakdown readability
- Manshin and Baksu mark effect readability
- matchmaker adjacent purchase prompt labeling
- locale persistence

Pre-fix failed coverage:

1. Character selection prompt overflows vertically on desktop: `bodyOverflowsY` was `true`.
2. Remote turn effect continuity could not find `spectator-turn-weather`.
3. Mixed participant clean-load test could not find `spectator-turn-panel`.
4. Remote timeout fallback test could not find `spectator-turn-panel`.
5. Mixed participant timeout/payoff handoff test could not find `spectator-turn-panel`.
6. Worker success/fallback continuity test could not find `spectator-turn-worker`.
7. Weather continuity test found projected economy text without the required text shadow.
8. Long worker-success-to-fallback chain test could not find `board-event-reveal-rent_paid-1`.
9. Repeated fallback continuity test could not find `board-event-reveal-fortune_resolved-1`.

Expected behavior:

- Every visible stage/spectator/effect surface must have stable test selectors that match the current rendered UI, not only older component names.
- `운수`, `잔꾀`, `날씨`, rent/payoff, worker fallback, and passive bonuses must remain visible through either a prompt-local context, reveal stack, spectator panel, stage panel, or event feed item.
- If the UI intentionally replaced `spectator-turn-panel` with another visual surface, the e2e contract should be updated with the new selector names and the old expectations removed.
- If the reveal/event feed is intentionally hidden until a user action, the toggle must be reachable and the resulting reveal items must be test-addressable.
- Character draft must fit within a normal desktop viewport without document-level vertical overflow.

Current assessment:

- This was not a Redis boot or storage failure. Redis-backed gameplay progressed and the browser stayed alive.
- Root cause was a UI contract/readability regression: the visible surface had moved, but spectator/core-action/reveal selectors and cause-first ordering were no longer preserved.
- The issue is closed after a green `npm run e2e:human-runtime` run plus the two browser parity trick lifecycle checks for `긴장감 조성` and `극심한 분리불안`.

### 2026-05-01 REDIS-UI-11 Resolved: Four-Player Draft Looked Like A Broken Three-Player Game

Status: RESOLVED
Severity: P0
Retest method: focused unit tests, 500-seed engine scan, and a live four-human websocket play session.
Live session: `sess_8IkhAJxSLizm49Ag6L2KJdHF`

Updated report from play: even after the round-start replay fix, draft order, target selection, and turn order still looked wrong. In the default seed path, a player could disappear from the first round before character draft, making the whole match behave like a malformed 3-player game.

Root cause:

- `prepare_run()` dealt the initial five trick cards before the first weather reveal.
- With seed `42`, the first weather was `긴급 피난`, which doubles burden cleanup cost.
- P3's initial public trick hand contained enough burden cleanup pressure to bankrupt the player before any draft or human decision.
- Because P3 was already dead at draft time, the first round only prompted the remaining three players. That made draft prompts, final character selection, `round_order`, and character start abilities look unrelated to the user's choices.
- A separate mark-target parser bug compounded the symptom: server-side choice parsing rebuilt mark choices without the original invocation args/kwargs, so legal mark choices could fail to resolve through the canonical decision gateway.

Fix:

- `GameEngine.prepare_run()` now creates the initial state without dealing trick cards.
- The first weather is still revealed before draft, but the initial trick hand is dealt immediately after that first weather reveal and before draft starts.
- Later rounds are unchanged: weather still applies to the existing hand at the start of the round.
- `DecisionGateway._parse_mark_target_choice()` now rebuilds mark-target choices with the actual invocation args/kwargs, preserving the live legal target context.
- The previous round-start prompt replay fix was kept: pending `draft_card` and `final_character` prompts rewind sequencing to the start of the round-start transition even if a stale prior `current_round_order` is still present in the checkpoint.

Validation:

```text
PYTHONPATH=/Users/sil/Workspace/project-mrn/GPT .venv/bin/python -m pytest GPT/test_rule_fixes.py -k 'mark_target or initial_weather or trick_visibility_reveals_all_but_one or hidden_trick_is_preserved_until_removed' -q
9 passed, 103 deselected

.venv/bin/python -m pytest apps/server/tests/test_runtime_service.py -k 'mark_target_context_uses_public_active_faces_for_future_slots or ai_bridge_keeps_mark_target_on_canonical_decision_flow or round_start_prompt_replay or hidden_trick' -q
7 passed, 77 deselected
```

Additional engine scan:

- Seeds `1..500` now produce `0` first-round pre-draft eliminations.

Live four-human validation:

- `round_start` reported `alive_player_ids: [1, 2, 3, 4]` even with first weather `긴급 피난`.
- Draft progressed through four first-pick prompts and four second-pick assignments.
- Final character prompts resolved for all four players.
- Hidden trick prompts resolved for all four players.
- `round_order` became `[3, 1, 2, 4]` with characters `{3: 자객, 1: 탈출 노비, 2: 박수, 4: 건설업자}`.
- P3's `자객` ability prompted `mark_target`, the selected `탈출 노비` target resolved to P1, and the stream emitted `mark_resolved`.
- The same turn then advanced through `trick_to_use` pass, `movement` dice choice, `dice_roll`, and `player_move`.
- All submitted decisions were accepted; no duplicate prompt, rejected ack, or runtime wait stall appeared.

Notes:

- The mark-target prompt intentionally shows public future priority-card faces, not only final confirmed character names. In the validated session that meant labels such as `파발꾼`, `교리 연구관`, and `객주` could appear because they were public card-face guesses for future slots. Selecting a held future public face now resolves correctly.
- This bug was not caused by another PC pulling a bad build. A stale build could keep showing old behavior, but the reproduced root cause was deterministic engine setup ordering in the current code path.
