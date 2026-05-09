# apps/server/tests

Server-side regression suite for the React/FastAPI online runtime.

## Coverage map

- `test_session_service.py`
  - session lifecycle rules (create/join/start/token/seat validation)
  - seat/token invariants used by runtime/auth layers
- `test_sessions_api.py`
  - REST lifecycle contract (`create`, `join`, `start`, `runtime-status`, `view-commit`, debug `replay`)
  - parameter-manifest propagation and shape validation
  - runtime start trigger checks for all-AI and mixed seats
- `test_stream_api.py`
  - websocket connect/resume latest-`view_commit` delivery
  - auth + decision-ack error guards
  - timeout fallback emission
  - manifest reconnect/rehydrate contract
  - recovery path (seat reconnect starts missing runtime task)
- `test_runtime_service.py`
  - runtime async bridge semantics
  - fallback history tracking
  - `recovery_required` diagnostics for in-progress session without runtime task

## Runtime flow invariants (must hold)

1. `POST /sessions/{id}/start` starts runtime task for a valid session start.
2. Mixed (human+AI) sessions must not be stuck at startup because of seat connection timing.
3. Spectator websocket connections must not mutate runtime execution state.
4. Seat websocket connection may trigger runtime task recovery, but live UI state must still come from cached `view_commit`.
5. Connect/resume sends the latest cached `view_commit`; live recovery must not replay event gaps.

## Test pipeline

- Fast local gate (server runtime core):
  - `python -m pytest apps/server/tests/test_session_service.py apps/server/tests/test_sessions_api.py apps/server/tests/test_stream_api.py apps/server/tests/test_runtime_service.py -q`
- Full server suite:
  - `python -m pytest apps/server/tests -q`

Recommended CI policy:

- Pull request required checks:
  - full server suite
  - web unit tests (`npm run test -- --run`)
- Release branch gate:
  - full server suite + web tests + authoritative view-commit/human-play acceptance run logs

## Known unstable / operational cautions (2026-03-31)

- After backend code changes, stale server processes can keep old runtime behavior.
  - Always fully restart the FastAPI process before validating runtime-start/recovery behavior.
- `runtime-status: recovery_required` can still appear transiently during startup/reconnect boundaries.
  - Treat it as a runtime diagnostic only; live render recovery must use `/view-commit` or websocket `view_commit`.
- Keep this file aligned with:
  - `docs/current/runtime/end-to-end-contract.md`
  - `docs/current/planning/[PLAN]_NEXT_WORK_PRIORITY_REFERENCE.md`
