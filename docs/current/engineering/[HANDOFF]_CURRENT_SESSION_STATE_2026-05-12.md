# Current Session Handoff - 2026-05-12

Updated: 2026-05-12 14:22:54 KST

This document is the handoff point for a new session. Read this first, then confirm with `git status --short`.

## Post-Commit Update

After this handoff was written, the listed code, test, and documentation changes were committed and pushed to `origin/main`.

Important caveat: the Codex shell for this session could modify workspace files but could not write `.git/index.lock`, so the commit was created through the GitHub Git Data API instead of local `git commit`. A fresh clone of `origin/main` has the committed content. This local checkout may still show the same files as modified until its Git metadata is refreshed outside the restricted shell.

The `.playwright-mcp/` local browser artifacts were intentionally excluded from the commit.

## Current Goal

The active goal is to make repeated headless protocol/RL game testing usable without filling the AI conversation context with raw logs.

The agreed structure is:

- `raw/`: large evidence files only.
- `summary/`: small AI-readable status and gate files.
- `pointers/`: failure lookup keys and log search hints.

The agent must read `summary/` first. Raw logs are not default context. Raw logs are only searched by the keys in `pointers/` when a failure requires investigation.

## Repository State

- Repository: `/Users/sil/Workspace/project-mrn`
- Branch: `main`
- HEAD: `a3a1d6a1 Enforce backend timing in protocol RL gate`
- `HEAD`, `origin/main`, and `origin/HEAD` currently point to the same commit.
- There are uncommitted changes.
- Do not assume all dirty files were changed in the latest turn. Some backend, engine, and headless changes were already present before the latest log-splitting implementation.

Recent commits:

```text
a3a1d6a1 (HEAD -> main, origin/main, origin/HEAD) Enforce backend timing in protocol RL gate
44b8ca16 Fix parallel protocol ACK latency
a0af90fb Merge branch 'codex/fail-fast-rl-protocol'
83e105b4 (origin/codex/fail-fast-rl-protocol, codex/fail-fast-rl-protocol) Fix concurrent protocol gate runtime boundary
e4ced5a1 Add protocol gate multi-game runner
```

## Dirty Worktree

`git status --short` at handoff:

```text
 M apps/server/src/services/realtime_persistence.py
 M apps/server/src/services/stream_service.py
 M apps/server/tests/test_redis_realtime_services.py
 M apps/server/tests/test_stream_service.py
 M apps/web/src/headless/fullStackProtocolHarness.spec.ts
 M apps/web/src/headless/fullStackProtocolHarness.ts
 M apps/web/src/headless/protocolGateRunArtifacts.spec.ts
 M apps/web/src/headless/protocolGateRunArtifacts.ts
 M apps/web/src/headless/runFullStackProtocolGate.ts
 M apps/web/src/headless/runProtocolGateGames.ts
 M docs/current/ai/rl-evaluation-gate.md
 M docs/current/engineering/[LESSONS]_REDIS_RUNTIME_UI_PLAYTEST.md
 M engine/runtime_modules/runner.py
 M engine/test_runtime_sequence_modules.py
?? .playwright-mcp/
?? apps/web/src/headless/protocolGateRunProgress.spec.ts
?? apps/web/src/headless/protocolGateRunProgress.ts
?? apps/web/src/headless/protocolLatencyGate.spec.ts
?? apps/web/src/headless/protocolLatencyGate.ts
?? docs/current/engineering/[HANDOFF]_CURRENT_SESSION_STATE_2026-05-12.md
```

Current diff stat excluding untracked files:

```text
 apps/server/src/services/realtime_persistence.py   | 136 +++++++++----
 apps/server/src/services/stream_service.py         |  59 ++++--
 apps/server/tests/test_redis_realtime_services.py  |  62 ++++++
 apps/server/tests/test_stream_service.py           |  31 +++
 .../src/headless/fullStackProtocolHarness.spec.ts  |  94 ++++++++-
 apps/web/src/headless/fullStackProtocolHarness.ts  | 221 ++++++++++++++++++++-
 .../src/headless/protocolGateRunArtifacts.spec.ts  |  25 ++-
 apps/web/src/headless/protocolGateRunArtifacts.ts  |  39 +++-
 apps/web/src/headless/runFullStackProtocolGate.ts  | 163 ++++++++++++++-
 apps/web/src/headless/runProtocolGateGames.ts      | 179 +++++++++++++++--
 docs/current/ai/rl-evaluation-gate.md              |  13 ++
 .../[LESSONS]_REDIS_RUNTIME_UI_PLAYTEST.md         |  11 +-
 engine/runtime_modules/runner.py                   |  26 +++
 engine/test_runtime_sequence_modules.py            |  83 ++++++++
 14 files changed, 1054 insertions(+), 88 deletions(-)
```

Untracked files:

```text
.playwright-mcp/console-2026-05-08T17-14-04-516Z.log
.playwright-mcp/console-2026-05-08T17-51-44-161Z.log
.playwright-mcp/console-2026-05-08T17-52-27-279Z.log
.playwright-mcp/page-2026-05-08T17-14-04-715Z.yml
.playwright-mcp/page-2026-05-08T17-14-28-663Z.yml
.playwright-mcp/page-2026-05-08T17-16-01-315Z.yml
.playwright-mcp/page-2026-05-08T17-18-34-764Z.yml
.playwright-mcp/page-2026-05-08T17-19-08-405Z.yml
.playwright-mcp/page-2026-05-08T17-19-31-692Z.yml
.playwright-mcp/page-2026-05-08T17-19-43-773Z.yml
.playwright-mcp/page-2026-05-08T17-51-44-349Z.yml
.playwright-mcp/page-2026-05-08T17-52-15-416Z.yml
.playwright-mcp/page-2026-05-08T17-52-27-417Z.yml
apps/web/src/headless/protocolGateRunProgress.spec.ts
apps/web/src/headless/protocolGateRunProgress.ts
apps/web/src/headless/protocolLatencyGate.spec.ts
apps/web/src/headless/protocolLatencyGate.ts
docs/current/engineering/[HANDOFF]_CURRENT_SESSION_STATE_2026-05-12.md
```

The `.playwright-mcp/` files look like local browser inspection artifacts. Do not commit them unless there is a concrete reason.

## Latest Completed Implementation

The latest task implemented the log/context separation for multi-game protocol gate runs.

Files changed or added for that specific goal:

- `apps/web/src/headless/protocolGateRunArtifacts.ts`
- `apps/web/src/headless/protocolGateRunArtifacts.spec.ts`
- `apps/web/src/headless/protocolGateRunProgress.ts`
- `apps/web/src/headless/protocolGateRunProgress.spec.ts`
- `apps/web/src/headless/runProtocolGateGames.ts`
- `docs/current/ai/rl-evaluation-gate.md`
- `docs/current/engineering/[LESSONS]_REDIS_RUNTIME_UI_PLAYTEST.md`

Implemented artifact layout:

```text
game-N/
  raw/
    backend_server.log
    progress.ndjson
    protocol_gate.log
    protocol_replay.jsonl
    protocol_trace.jsonl
  summary/
    failure_reason.json
    gate_result.json
    progress.json
    run_status.json
    slowest_command.json
    slowest_transition.json
    summary.json
  pointers/
    failure_pointer.json
    log_offsets.json
    suspect_events.json
```

Important behavior:

- `runProtocolGateGames.ts` creates `raw/`, `summary/`, and `pointers/` per game.
- Child stdout and stderr are written to `raw/protocol_gate.log`.
- Compact progress is printed as one-line `PROTOCOL_GATE_GAME_PROGRESS` events.
- Compact progress records are persisted to `raw/progress.ndjson`.
- Latest small status files are written to:
  - `summary/run_status.json`
  - `summary/progress.json`
  - `summary/slowest_command.json`
- Terminal gate files are written to:
  - `summary/gate_result.json`
  - `summary/slowest_transition.json`
- On failure, the runner writes:
  - `pointers/failure_pointer.json`
  - `summary/failure_reason.json`
  - `pointers/suspect_events.json`
  - `pointers/log_offsets.json`
- The runner sets a default `--backend-log-out` to `raw/backend_server.log` unless the caller explicitly passes one.
- The help text explicitly forbids using shell `tee` as the source of truth and points agents to `summary/gate_result.json` first.

## Tests Already Run

The latest implementation used test-first flow.

Targeted tests passed:

```bash
npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts
```

Result:

- 3 test files passed.
- 10 tests passed.

Build passed:

```bash
npm --prefix apps/web run build
```

Result:

- Build completed.
- Vite reported chunk-size warnings after minification. This is not a failure introduced by the latest log-splitting change.

## Earlier Active Work Still In Worktree

Several dirty files reflect earlier work around runtime protocol stability, backend timing gates, Redis/realtime stream behavior, and engine module timing.

Do not revert these without explicit instruction:

- `apps/server/src/services/realtime_persistence.py`
- `apps/server/src/services/stream_service.py`
- `apps/server/tests/test_redis_realtime_services.py`
- `apps/server/tests/test_stream_service.py`
- `apps/web/src/headless/fullStackProtocolHarness.ts`
- `apps/web/src/headless/fullStackProtocolHarness.spec.ts`
- `apps/web/src/headless/runFullStackProtocolGate.ts`
- `apps/web/src/headless/protocolLatencyGate.ts`
- `apps/web/src/headless/protocolLatencyGate.spec.ts`
- `engine/runtime_modules/runner.py`
- `engine/test_runtime_sequence_modules.py`

Known intent of earlier work from current context:

- Runtime command boundary was tightened so internal module transitions are not treated as Redis/view authoritative commits.
- Protocol/RL gate was expanded to track backend timing, command latency, stale/refused/failed commands, duplicate handling, and fail-fast behavior.
- Multi-game and parallel protocol gate runs were introduced.
- A protocol command latency threshold was moved to 5 seconds for the current learning-loop gate.
- The latest user direction was to stop loading or streaming large logs into the AI context and make scripts produce compact status artifacts instead.

## Documentation Updated

`docs/current/ai/rl-evaluation-gate.md` now documents:

- multi-game runner artifact layout,
- `summary/`, `pointers/`, `raw/` read order,
- prohibition on default raw-log loading,
- using `summary/gate_result.json` and `summary/failure_reason.json` before touching raw logs.

`docs/current/engineering/[LESSONS]_REDIS_RUNTIME_UI_PLAYTEST.md` now documents:

- multi-game protocol gate runs must use the runner, not ad hoc `for` plus `tee`,
- each `game-N/` directory must be self-contained,
- long runs must not stream progress JSON into the agent conversation,
- raw logs must be searched by pointer fields instead of loaded wholesale.

## Why This Was Needed

The prior workflow repeatedly caused context compression because:

- test output was large,
- raw protocol logs and Docker/backend logs were being inspected directly,
- long-running tests emitted too much progress into the conversation,
- the agent sometimes watched output instead of reading compact script-produced status.

The fix is not to ask the agent to "watch less"; the script must create the right surfaces:

- compact progress line for humans and agents,
- small JSON status files for current state,
- failure pointers for targeted raw-log lookup,
- raw logs kept outside normal context.

## Current Completion Criteria

This handoff is complete only if the next session can:

1. Open this file.
2. Run `git status --short`.
3. Understand that the repo is dirty and not fully committed.
4. Know that latest log-splitting tests and build passed.
5. Know not to read full raw logs by default.
6. Continue with either commit preparation or the next protocol gate run.

## Recommended Next Steps

1. Confirm current status:

   ```bash
   git status --short
   ```

2. Inspect only relevant diff before committing:

   ```bash
   git diff -- apps/web/src/headless/protocolGateRunArtifacts.ts apps/web/src/headless/protocolGateRunProgress.ts apps/web/src/headless/runProtocolGateGames.ts
   git diff -- docs/current/ai/rl-evaluation-gate.md docs/current/engineering/[LESSONS]_REDIS_RUNTIME_UI_PLAYTEST.md
   ```

3. Re-run the latest targeted verification if needed:

   ```bash
   npm --prefix apps/web test -- src/headless/protocolGateRunArtifacts.spec.ts src/headless/protocolGateRunProgress.spec.ts src/headless/protocolLatencyGate.spec.ts
   npm --prefix apps/web run build
   ```

4. Before a broad commit, decide whether to include only the latest log-splitting files or also the earlier backend/engine/protocol-gate changes.

5. Do not commit `.playwright-mcp/` unless those artifacts are intentionally required.

6. For the next 5-game or 10-game test, read generated outputs in this order:

   ```text
   game-N/summary/gate_result.json
   game-N/summary/run_status.json
   game-N/summary/progress.json
   game-N/summary/slowest_command.json
   game-N/summary/slowest_transition.json
   game-N/summary/failure_reason.json
   game-N/pointers/failure_pointer.json
   game-N/pointers/suspect_events.json
   game-N/pointers/log_offsets.json
   ```

   Only then search `game-N/raw/` with the pointer keys.

## Known Caution

There is a small implementation concern in `runProtocolGateGames.ts`: progress-summary writes are chained through `writeChain = writeChain.then(...)`. If one async write fails, later writes will also reject during flush. That is acceptable because the test run should fail instead of hiding artifact write failure. If this becomes noisy, handle it deliberately by recording the first write failure and surfacing it once at flush.

## Do Not Repeat

- Do not use ad hoc shell loops plus `tee` for multi-game evidence.
- Do not pipe or paste full protocol logs into the AI conversation.
- Do not treat raw logs as the primary status surface.
- Do not investigate a failed run by reading full `backend_server.log` first.
- Do not revert unrelated dirty files.
- Do not claim all current dirty changes belong to the latest task.
