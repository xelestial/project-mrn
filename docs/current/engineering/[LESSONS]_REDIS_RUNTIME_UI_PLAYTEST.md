# Redis Runtime UI Playtest Lessons

Status: ACTIVE
Updated: 2026-05-09

## 1. Ownership

Redis timing was not the main instability class. Failures came from unclear ownership between engine modules, backend continuation checkpoints, and frontend projections.

Current rule: engine modules own progress, Redis stores checkpoints, backend validates continuations, frontend renders projections.

Module boundaries are not Redis boundaries. A module test verifies responsibility, input, output, and interface contracts without Redis, WebSocket, or `view_commit`. Redis belongs to runtime persistence/recovery tests; `view_commit` belongs to frontend projection/integration tests.

User command boundaries are the default persistence boundaries. A button press such as movement or purchase should create a lightweight command lifecycle record (`processing -> success/refused/failed/waiting_input`), run internal validators/resolvers in memory, and publish a final authoritative state/view only when the command reaches an external boundary.

Irreversible inputs are the exception, not an excuse for per-module commits. Dice rolls, ordered deck draws such as fortune/weather, and accepted reward outcomes must be persisted because replay must consume the same value. Turn pointers, validator failures, hidden-trick availability, movement substeps, and purchase substeps should stay inside the command runner until a terminal boundary. If replay needs a value, persist that value; do not persist every transition that happened to use it.

Frontend duplicate submissions are absorbed by idempotency, not by hoping the browser sends only once. The UI must single-flight by active prompt, player, and action; reconnect recovery must check pending command status and the latest `view_commit` before retrying; the backend must treat a repeated `request_id` as a dedupe hit or explicit stale/refused result.

## 2. Prompt Lifecycle

Every prompt must close through an explicit phase-progress event or a stored continuation result. Acknowledgement events alone are not enough for reconnect, replay, or delayed follow-up prompts.

Covered prompt classes:

- draft/final character
- trick choice and hidden trick follow-up
- mark target
- movement
- purchase
- LAP reward
- simultaneous resupply

## 3. Resume Boundaries

Resume must use the stored frame/module cursor:

- trick follow-ups stay inside `TrickSequenceFrame`
- fortune movement stays inside `FortuneResolveModule -> MapMoveModule -> ArrivalTileModule`
- simultaneous resupply stays inside `SimultaneousResolutionFrame`
- round-start draft/final-character prompts preserve the original decision order

The backend must not infer resume position from card names, localized labels, request-id arithmetic, or frontend state.

## 4. Frontend Recovery

Frontend recovery must preserve the latest authenticated `view_state` and must not resurrect closed prompts after replay or reconnect.

Stable selectors are part of the UI contract. Replacing a visual surface requires equivalent stable selectors before tests move.

## 5. Required Evidence

- server continuation mismatch tests
- command wakeup resume tests
- frontend prompt close/recovery tests
- browser parity checks for trick follow-up and spectator evidence
- manual playtest after automated suites pass

## 6. Headless RL Protocol Lessons

The headless RL adapter is a protocol tester, not an engine shortcut. It must follow the same REST session creation, WebSocket join/resume, prompt ledger, decision submission, decision acknowledgement, and `view_commit` path that browser play uses.

Lesson from 2026-05-09: waiting for a server timeout while the same active prompt remains visible is a bug. A round has a bounded number of possible prompt sites: global prompts, other players' turns, and the current player's turn. If a single player appears to accumulate decisions alone, the test must treat it as protocol desynchronization until logs prove otherwise.

Required rule:

- Never classify repeated same-player decisions as "normal waiting" without checking `request_id`, `view_commit_seq_seen`, decision ACK, server `decision_received`, Redis command stream, and fallback records.
- If the same active prompt is still visible and no ACK arrives, the headless client must not resend only because time passed. Browser play does not auto-click again after an ACK delay.
- Resend is allowed only after reconnect exposes the same active prompt, because that is a real delivery-loss boundary. It must be bounded and separately counted as `unackedDecisionRetryCount`.
- Simultaneous prompt decisions can arrive while the runtime is already processing another accepted command. `command_processing_already_active` is a deferral, not a terminal result. The wakeup task must retry the accepted command; otherwise the session can wait on a prompt whose decision is already accepted.
- A decision accepted against the stored checkpoint continuation must not be rejected only because a replayed prompt envelope regenerates a different legal-choice list. The stored continuation is the authoritative contract; regenerated legal-choice drift is a diagnostic event and must be fixed from logs/tests without hiding the accepted command.
- Runtime command rejection must be persisted and exposed through runtime status. If rejection is only visible in server logs while `/runtime-status` still reports `waiting_input`, the headless adapter will wait until idle timeout and misreport a hard protocol failure as slow play.
- Protocol-gate live runs use the protocol compose stack on `127.0.0.1:9091`. Running the same command against `9090` validates the normal local backend and can hide whether the rebuilt protocol stack is actually under test.
- Multi-game protocol-gate runs must use `npm run rl:protocol-gate:games`, not an ad hoc `for` loop piped through `tee`. `npm --prefix apps/web` and shell redirection resolve relative paths from different directories, so the runner owns all artifact paths and writes `summary.json` through `--summary-out`.
- A stale ACK caused by a recovered unacked resend is not the same as an unrecovered stale decision. The quality gate must distinguish the two.
- The default headless policy must not blindly choose the first non-secondary legal choice for repeatable optional prompts. `burden_exchange` offers `yes` before `no`; repeatedly choosing `yes` turns a normal supply step into a maximal churn scenario and invalidates "fast familiar click" timing evidence.
- `decision_timeout_fallback_seen`, rejected ACK, Redis fallback entry, or unmatched Redis command count is a failure for RL stability testing.
- "One game completed" is not enough evidence. The report must include wall time, app duration, per-command timing, trace decision counts, server decision counts, Redis command counts, fallback counts, and per-seat client metrics.
- One-game duration is a guardrail. Human play is slow when players deliberate to win; the protocol path itself is not slow. If one familiar operator can click through the normal game flow within 10 minutes without strategic deliberation, a headless run that exceeds 10 minutes is presumed stuck or desynchronized until the logs prove otherwise.
- A timeout worker must claim the pending prompt before executing fallback. A stale Redis pending snapshot is evidence to re-check state, not permission to append fallback after normal decision acceptance already removed the prompt.
- A late-game timestamp must be split by command timing before blaming policy speed. In the 2026-05-09 headless run, `command_seq=78` spent 8461ms across 13 normal module transitions and opened `r2:t7:p4:hidden_trick_card:65`; `command_seq=79` rejected the accepted choice in 76ms, then runtime status kept reviving the checkpoint as `waiting_input` for 60359ms. That is not slow decision making. It is a fail-fast/status exposure bug plus a replay legal-choice drift bug.
- Hidden trick resume is checkpoint-authoritative. If the stored prompt accepted choice `14` but replay regeneration now offers `12/17/20`, the backend must expose that drift and continue from the checkpoint-validated payload instead of rejecting and waiting. The follow-up task is to fix the engine/module mutation boundary that caused the regenerated hand to differ.
- A time-based unacked resend can create a false stale decision. In `sess_fT6B5tyTvbhJUoncx5yjYD26`, `r1:t5:p1:active_flip:62` was accepted, then the command advanced through round cleanup and opened the next round prompt in 4375ms. The headless 5s unacked retry sent the old request again and the backend correctly rejected it as `stale_prompt_request`. That retry is not browser-equivalent and must stay disabled outside reconnect recovery.
- Per-command duration must include internal transition cost. In `sess_fT6B5tyTvbhJUoncx5yjYD26`, `command_seq=95` took 10991ms across 15 transitions; per-module Redis commits alone accounted for roughly 5.4s. A long turn can be backend persistence overhead even when every prompt decision is immediate.
- Do not confuse modularity with external commits. Modularity means `PurchaseValidator`, `MovementResolver`, `ArrivalResolver`, and similar units keep narrow contracts and can be tested with pure in/out state. It does not mean every internal step writes Redis, rebuilds frontend projection, or emits a `view_commit`.
- Command-boundary staging must skip expensive external preparation. In the 2026-05-09 fix, internal non-terminal transitions stage only in-memory state. They must not read source history, build authoritative `view_commit`, validate precommit view payloads, or write Redis. Terminal boundaries still commit exactly once.
- Command-boundary staging also applies to runtime status persistence. A non-terminal internal transition may update in-process status for the current runner, but it must not write runtime status to Redis as a substitute progress log. Command lifecycle status is recorded at command acceptance and terminal boundary; module-by-module status belongs in `module_trace`.
- Nonblocking human prompts are runtime boundaries, not gateway publish boundaries. The decision gateway may create or reuse the pending prompt and raise `PromptRequired`, but it must not synchronously publish WebSocket events, mark delivery, or emit decision-requested records before the runtime has committed the terminal `waiting_input` boundary. Otherwise a prompt handoff can block inside the command runner and reintroduce multi-second latency even when Redis/view commits are already bounded.
- A high `module_transition_count` is not itself a Redis bug. It means one accepted command advanced through several pure engine modules before the next external prompt. Treat it as suspicious only if it pairs with repeated Redis/view commits, repeated hydrate/prepare, or module timings that exceed the command SLA.
- A repeated prompt signature is a state-machine bug until proven otherwise. If the same `active_module_id`, player, request type, round, and turn keep producing new `request_id` values, the module is not recording its continuation progress. Multi-prompt engine actions must either persist their substep/result in the action payload before raising `PromptRequired`, or split the work into separate actions/modules with explicit contracts.
- The 2026-05-09 `FortuneResolveModule` loop was not caused by Redis/view commits. `resolve_fortune_forced_trade` asked for `trade_own_tile`, then suspended at `trade_other_tile`; replay restarted from the first target because the first target was not checkpointed. The fix class is structural: save the consumed first target in the action payload at the prompt boundary and add a headless repeated-prompt gate.

Minimum comparison after every headless live RL run:

- trace `decision_sent` equals server `decision_received`
- trace `decision_ack` equals Redis `decision_submitted`
- rejected/stale/fallback/send-failure/client-error counts are zero, except recovered stale ACKs explicitly paired with bounded unacked resends
- Redis fallback list is empty
- per-seat accepted decisions are plausible for the observed prompt counts; any seat-only buildup is investigated before continuing training
