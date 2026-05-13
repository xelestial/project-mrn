# Redis Runtime UI Playtest Lessons

Status: ACTIVE
Updated: 2026-05-13

This document keeps durable lessons only. Run-specific evidence belongs in protocol-gate artifacts, architecture audits, or bug reports.

Core lesson: do not repair a broken runtime contract by piling symptom-specific patches around it. If a patch needs a read model, heartbeat, duplicated wakeup path, or test-only runtime branch to compensate for missing authoritative state, the contract is still broken. Fix the ownership boundary first.

## 1. Authority Boundaries

Redis timing was not the main instability class. The repeated failures came from unclear ownership between engine modules, backend continuation checkpoints, prompt state, and frontend projections.

Current ownership rule:

- Engine modules own rule progress and legal state transitions.
- Redis stores authoritative checkpoints, pending prompts, accepted commands, command lifecycle state, and recovery data.
- Backend services validate continuations and run commands from stored boundaries.
- Frontend renders server projections. It does not become an authority source.

`view_commit` is a read model. It may be the frontend restore surface, but it must not be the server-side source of truth for accepting a decision or reconstructing a pending prompt.

`module_trace` and source events are diagnostic or replay evidence. They are not authoritative frontend render state and must not substitute for the final cached `view_commit`.

## 2. Prompt And Decision Lifecycle

Pending prompt state is the decision contract. A valid decision is accepted against the stored pending prompt or stored checkpoint continuation, not against a prompt reconstructed from UI projection.

Every interactive prompt must have a single owner:

- request id
- prompt instance id
- player id
- resume token
- frame/module cursor
- legal choices or resolver contract

The backend must not infer resume position from card names, localized labels, request-id arithmetic, or frontend state.

Duplicate submissions are handled by idempotency. The UI should single-flight by active prompt, player, and action; the backend must treat repeated `request_id` values as dedupe hits or explicit stale/refused results. Browser-equivalent clients do not resend the same decision only because time passed. Resend is allowed only after reconnect exposes the same active prompt and must be bounded and counted separately.

Decision ACK is client feedback. It is not an authoritative game-state transition. If ACK delivery needs stream replay/debug/outbox persistence, those auxiliary writes must be pipelined as one publish unit and must not become multiple serialized Redis round trips under the per-session stream lock.

## 3. Command And Runtime Boundaries

Module boundaries are not Redis boundaries. A module test verifies responsibility, input, output, and interface contracts without Redis, WebSocket, or `view_commit`.

User command boundaries are the default persistence boundaries. A button press such as movement or purchase should create a lightweight command lifecycle record, run internal validators/resolvers in memory, and publish authoritative state only when the command reaches an external boundary:

- `success`
- `refused`
- `failed`
- `waiting_input`
- `completed`

Irreversible inputs are the exception, not an excuse for per-module commits. Dice rolls, ordered deck draws, and accepted reward outcomes must be persisted because replay must consume the same value. Turn pointers, validator failures, movement substeps, purchase substeps, and similar internal progress should stay inside the command runner until a terminal boundary. If replay needs a value, persist that value; do not persist every transition that used it.

Command-boundary staging must skip expensive external preparation. Non-terminal transitions must not read full source history, build authoritative `view_commit`, validate precommit view payloads, write Redis checkpoints, or write runtime status as a substitute progress log. Module-by-module progress belongs in `module_trace`.

There must be one clear runtime wakeup owner per accepted command. A route-level wake task and a command-stream worker can coexist only if one is the primary path and the other is an explicitly bounded fallback. If both independently drive `process_command_once`, the system becomes hard to reason about under load.

The Redis command-stream watcher must not impersonate the runtime executor. Its job is recovery observation and wake signaling. If it directly calls the runtime fallback, ownership is split again and every timing or duplicate-processing investigation has two possible executors.

The command router must not create a hidden local executor when the session-loop manager is missing. A missing manager is a configuration failure or a degraded test fixture, not permission to call `RuntimeService.process_command_once()` directly. Skipping with a structured reason is better than reviving split ownership.

A disabled recovery worker must not advance a durable command consumer offset. If it records `runtime_wakeup` progress while not actually handing the command to the runtime owner, the next active loop will skip a valid accepted command.

A session-loop wakeup dedupe is safe only if the active drain owns the backlog until it is idle or blocked. If a drain stops at an artificial per-wakeup command budget, wakeups that arrived during that drain have already been deduped and cannot be relied on to restart it.

Do not mistake single-server saturation for Redis contention. In the 2026-05-12 20-game single-server stress run, the failed backend timing gate was caused by `InitialRewardModule` engine transition wall time above 5000ms. Redis commit and view projection stayed small on the same events. That points to server process execution capacity and transition scheduling, not Redis isolation, as the next bottleneck surface.

## 4. Frontend And Headless Protocol

The headless RL adapter is a protocol tester, not an engine shortcut. It must follow the same REST session creation, WebSocket join/resume, prompt ledger, decision submission, decision ACK, command processing, and `view_commit` path that browser play uses.

Frontend recovery must preserve the latest authenticated `view_state` and must not resurrect closed prompts after replay or reconnect.

Stable selectors are part of the UI contract. Replacing a visual surface requires equivalent stable selectors before tests move.

Long protocol-gate runs must keep the agent conversation small. Store detailed stdout/stderr and progress logs under the run artifact root, then inspect compact summaries and pointer files first.

Minimum comparison after every headless live RL run:

- trace `decision_sent` equals server `decision_received`
- trace `decision_ack` equals Redis `decision_submitted`
- rejected/stale/fallback/send-failure/client-error counts are zero, except recovered stale ACKs explicitly paired with bounded reconnect recovery
- Redis fallback list is empty
- per-seat accepted decisions are plausible for the observed prompt counts
- command timing and browser-observed prompt-to-ACK timing are reported separately

## 5. Failure Classification

Do not classify repeated same-player decisions as normal waiting without checking request id, `view_commit_seq_seen`, decision ACK, server `decision_received`, Redis command stream, and fallback records.

A same active prompt that remains visible without ACK is protocol desynchronization until logs prove otherwise. A stale ACK caused by recovered reconnect retry is different from an unrecovered stale decision and must be classified separately.

Runtime command rejection must be persisted and exposed through runtime status. If rejection is only visible in server logs while runtime status still reports `waiting_input`, headless clients will wait until idle timeout and misreport a status exposure bug as slow play.

A repeated prompt signature is a state-machine bug until proven otherwise. If the same active module, player, request type, round, and turn keep producing new request ids, the module is not recording continuation progress.

A zero-choice interactive prompt is a contract failure, not a frontend edge case. Empty candidate sets must resolve as no-op, refused, or partial success inside the engine/backend contract.

## 6. 2026-05-12 Server Structure Lessons

The latest server-structure diagnosis confirmed a sharper lesson: a read model must never repair or validate the write model.

Observed structural faults:

- Decision validation reads latest `view_commit` active prompt before accepting a decision.
- Missing pending prompt can be recreated from `view_commit.view_state.prompt.active`.
- Heartbeat can resend latest `view_commit`, giving heartbeat a repair role instead of a pure liveness role.
- Runtime wakeup used to exist in both the decision route and `CommandStreamWakeupWorker`; the rebuild now routes accepted command execution through `SessionLoopManager`, with the worker acting only as a Redis recovery watcher.
- Runtime status is split between in-process task state and Redis-backed recovery state.
- Source events and `view_commit` are not fully independent; source projection feeds parts of view state.
- Non-Lua Redis decision acceptance fallback can allocate command sequence outside the final append transaction.
- Production runtime behavior used to depend on `PYTEST_CURRENT_TEST` for AI delay defaults; this was removed in the server runtime rebuild and replaced with explicit runtime configuration.

Durable rules from this diagnosis:

- Do not keep adding compensating paths around a broken server contract; remove the contract ambiguity.
- Validate decisions against pending prompt state or checkpoint continuation, not against `view_commit`.
- Do not recreate authoritative pending prompt state from a frontend projection.
- Keep heartbeat as connection liveness. Snapshot or resume repair should be explicit and separately named.
- Keep one primary command wakeup/executor path per session.
- Runtime status exposed to clients must be recoverable from Redis, not only from in-process task memory.
- Redis fallbacks must fail closed or preserve the same atomicity contract as the primary path.
- Test speed knobs must be explicit configuration, not production branches on test-runner environment variables.

## 7. Required Evidence Before Claiming Stability

Required checks:

- server continuation mismatch tests
- command wakeup resume tests
- frontend prompt close/recovery tests
- browser parity checks for trick follow-up and spectator evidence
- full-stack protocol gate using the same stack and ports under test
- multi-game protocol-gate evidence stored under each `game-N/` artifact directory
- summary files for wall time, app duration, per-command timing, transition timing, decision counts, ACK counts, Redis command counts, fallback counts, and per-seat client metrics

One completed game is not sufficient evidence. Stability claims require repeated protocol-equivalent runs with zero unexplained stale, fallback, rejected ACK, unmatched Redis command, send failure, or client error counts.
