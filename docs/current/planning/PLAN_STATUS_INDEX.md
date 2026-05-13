# PLAN Status Index

Status: ACTIVE  
Updated: 2026-05-13
Owner: Engine runtime

## Purpose

This file answers one question only:

What documents still matter right now?

## Current Repo State

The broad architecture migration era is closed enough. Current work should start
from the runtime contracts, current gameplay rules, and the short priority board
instead of reopening broad umbrella plans.

Current repo-side work has six active tracks:

1. Runtime contract and modular-runtime stabilization
2. Redis-authoritative game state and visibility projection hardening
3. UI/UX readability follow-up from the current canonical frontend baseline
4. Real human/local-AI/external-AI playtest stabilization
5. Runtime protocol identity, prompt lifecycle, viewer outbox, and WebSocket
   recovery stabilization
6. Server runtime rebuild after the 2026-05-12 structure diagnosis

The 2026-05-02 modular runtime migration plans are implemented and no longer
kept as active execution context.
The current source of truth for that surface is now:

- `docs/current/runtime/end-to-end-contract.md`
- `docs/current/runtime/round-action-control-matrix.md`
- `engine/runtime_modules/`
- `apps/server/src/services/runtime_service.py`

## Canonical Current Documents

Read and maintain these:

1. `docs/current/engineering/MANDATORY_PRINCIPLES_AND_REQUIRED_PLAN_READING.md`
2. `docs/current/Game-Rules.md`
3. `docs/current/planning/PLAN_NEXT_WORK_PRIORITY_REFERENCE.md`
4. `docs/current/planning/PLAN_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md`
5. `docs/current/runtime/end-to-end-contract.md`
6. `docs/current/runtime/round-action-control-matrix.md`
7. `docs/current/frontend/ACTIVE_UI_UX_FUTURE_WORK_CANONICAL.md`
8. `docs/current/engineering/WORKLOG_IMPLEMENTATION_JOURNAL.md`
9. `docs/current/engineering/PLAN_REDIS_AUTHORITATIVE_GAME_STATE.md`
10. `docs/current/backend/runtime-logging-policy.md`
11. `docs/current/engineering/PLAN_TILE_TRAIT_ACTION_PIPELINE.md`
12. `docs/current/architecture/PLAN_SERVER_RUNTIME_REBUILD_2026-05-12.md`

## Current Reference Sets

- API and server contracts: `docs/current/api/`, `docs/current/backend/`
- Frontend baseline and audit: `docs/current/frontend/`
- Runtime contracts: `docs/current/runtime/`
- Rule/balance/reference material: `docs/current/rules/`
- External AI operation: `docs/current/engineering/EXTERNAL_AI_WORKER_RUNBOOK.md`
- Human/external AI playtest checklist: `docs/current/engineering/HUMAN_EXTERNAL_AI_PLAYTEST_CHECKLIST.md`
- Current runtime/external evidence:
  `docs/current/engineering/EVIDENCE_RUNTIME_CONTRACT_EXTERNAL_CHECKS_2026-05-04.md`
- Final local manual playtest evidence:
  `docs/current/engineering/EVIDENCE_FINAL_MANUAL_PLAYTEST_2026-05-04.md`
- Current server runtime rebuild:
  `docs/current/architecture/PLAN_SERVER_RUNTIME_REBUILD_2026-05-12.md`
  Current server-runtime rebuild work has removed direct runtime execution
  fallback from wakeup paths and split route-level command recovery queries into
  `CommandRecoveryService`; command precondition and stale terminal handling now
  live in `CommandProcessingGuardService`; in-process active command/task gating
  lives in `CommandExecutionGate`; command-boundary deferred commit finalization
  lives in `CommandBoundaryFinalizer`; command-boundary staging/deferred commit
  now lives in `CommandBoundaryGameStateStore` instead of a `RuntimeService`
  private class; command-boundary final commit now rechecks runtime lease
  ownership before authoritative Redis/view/prompt side effects; `SessionLoop`
  now owns command lifecycle control flow through `SessionCommandExecutor` and
  no longer falls back to `RuntimeService.process_command_once()`;
  `DecisionGateway` no longer owns process-local/random request id fallback for
  human prompt retry or AI decision events; `_LocalHumanDecisionClient` no
  longer uses engine `HumanHttpPolicy._prompt_seq` as its private prompt
  sequence source; prompt replay probing is now nonblocking on the live
  prompt-creation path; HTTP external AI now stops at a provider=`ai` pending
  prompt boundary and callback decisions re-enter through
  `PromptService`/`CommandInbox` before `CommandRouter` wakeup;
  simultaneous batch prompt submit and timeout fallback now enter
  `BatchCollector` instead of appending per-player decision commands, and
  completed batches re-enter `SessionLoop` as one `batch_complete` command;
  `RuntimeService.process_command_once()` compatibility wrapper has been
  removed; tests and production paths use `SessionCommandExecutor` directly.
  `CommandBoundaryGameStateStore` removal was reviewed and rejected for the
  current phase because it is the active staging boundary that prevents
  non-terminal transitions inside one accepted command from becoming multiple
  authoritative Redis/view/command commits. Removal requires a future
  UnitOfWork-style owner in `SessionLoop` or `SessionCommandExecutor`, not an
  in-place deletion.
  Out-of-process HTTP external AI full-stack
  evidence now uses the admin/worker bridge; local AI and loopback external AI
  remain local/test-profile paths, not operating external-worker evidence.
  Future loopback removal or HTTP convergence requires a separate migration
  instead of a forced in-place patch. One-server capacity is now classified:
  five and eight concurrent games passed, ten concurrent games first breached
  the 5s backend command SLO, and twenty concurrent games remains overload
  evidence. The current direction is measured horizontal server-instance scaling,
  not Redis fan-out or prompt/view-commit patching.

## Closed Enough

These are not active broad implementation tracks anymore:

- broad architecture migration
- decision-contract unification as a repo-wide plan theme
- string/resource migration as a standalone track
- parameter-decoupling as a standalone track
- quarter-view board/event presentation as a standalone frontend rebuild plan
- desktop turn overlay / board readability as a standalone plan

Those themes should reopen only if a concrete regression or rollout need appears.

## Remaining Open Work

1. Redis-authoritative game state migration. Redis-backed rooms, sessions,
   streams, prompts, runtime metadata, command streams, prompt timeout worker
   service/entrypoint, command wakeup worker service/entrypoint, Docker Compose
   local worker wiring, local JSON archive export, live checkpoint/view-state
   storage, canonical GameState checkpoint serialization/hydration, recovery
   checkpoint fixture, restart integration coverage, Redis-persisted command
   worker offsets, Lua-backed command/lease primitives, command-triggered
   transition commit metadata, Redis hash-tag health reporting, local backend
   restart smoke, authenticated REST restart recovery, worker readiness
   commands, production-like smoke flags, the role/process deployment contract,
   platform-managed manifest template, executable local platform-managed smoke
   profile, custom-command restart-smoke input path, manifest-driven platform
   smoke runner, structured smoke evidence artifact output, explicit
   local-vs-external topology validation, post-restart decision smoke/dedupe
   proof, and structured smoke evidence checks for waiting state, replay
   monotonicity, Redis hash tag, worker health, single accepted decision,
   duplicate rejection, and replay advancement are implemented. Remaining work
   is replacing the platform manifest placeholders with the chosen deployment
   platform's native restart/exec commands, running that filled manifest through
   the platform smoke runner with `--require-external-topology`, and capturing
   smoke evidence from the actual external topology. The 2026-05-04 evidence
   pass confirmed that the local manifest validates and that
   `--require-external-topology` correctly rejects local-only evidence. See
   `docs/current/engineering/PLAN_REDIS_AUTHORITATIVE_GAME_STATE.md`.
2. Runtime protocol and contract stabilization. The current baseline is guarded
   by `docs/current/planning/PLAN_RUNTIME_PROTOCOL_STABILITY_AND_IDENTITY.md`,
   the module-runtime matrix, native module/semantic-guard/continuation and
   idempotency tests, and frontend decision/prompt contract tests. Keep
   end-to-end payload shape, round/action control, prompt lifecycle, and
   modular-runtime frame semantics synchronized between `engine/`,
   `apps/server/`, and `apps/web/` as new rule changes land. The Phase 0
   checklist in the protocol plan is synchronized to the current 2026-05-13
   implementation evidence; request IDs and prompt instance IDs remain explicit
   residual migration boundaries rather than hidden completion.
3. UI/UX follow-up. Effect cause visibility now preserves backend
   `effect_context` source player, source family, source name, and resource
   delta through the prompt overlay. The 2026-05-04 automated evidence pass
   confirms backend projection, frontend selector/overlay rendering, and the
   18-test `e2e:human-runtime` gate. The final local 2H+2AI and 4-human manual
   playtest evidence also passed, including active-weather context visibility.
   Use only
   `docs/current/frontend/ACTIVE_UI_UX_FUTURE_WORK_CANONICAL.md` and
   `docs/current/frontend/AUDIT_MRN_FRONTEND_GAME_DESIGN_REVIEW_2026-04-30.md`
   as current frontend planning inputs.
4. External AI endpoint operation. Local worker behavior is verified through
   the worker API tests and priority-scored worker runbook smoke. The game
   server HTTP external-AI path no longer calls the worker directly inside the
   session loop; it now waits on a provider=`ai` prompt and accepts the later
   callback through the same decision command path as human decisions. Remote
   evidence commands now have fail-closed flags requiring a non-local server,
   non-local worker, worker auth, and summary-file output. A remote non-local
   external AI endpoint still needs its actual base URL and credential/config
   values before it can be called deployment evidence.

## Rule For New Work

Do not reopen broad architecture or migration documents by default.

If a new task appears:

1. start from current rules
2. start from this index and the next-work board
3. start from the runtime/frontend/API contracts for the touched surface
4. start from playtest evidence when behavior is uncertain
5. record new decisions in the worklog instead of reviving broad umbrella plans
