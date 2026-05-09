# Redis Runtime UI Playtest Lessons

Status: ACTIVE
Updated: 2026-05-09

## 1. Ownership

Redis timing was not the main instability class. Failures came from unclear ownership between engine modules, backend continuation checkpoints, and frontend projections.

Current rule: engine modules own progress, Redis stores checkpoints, backend validates continuations, frontend renders projections.

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
- If the same active prompt is still visible and no ACK arrives, the headless client may resend the same already-selected decision with a fresh client sequence. It must not run the policy again for that prompt.
- Resend must be bounded and separately counted as `unackedDecisionRetryCount`.
- A stale ACK caused by a recovered unacked resend is not the same as an unrecovered stale decision. The quality gate must distinguish the two.
- `decision_timeout_fallback_seen`, rejected ACK, Redis fallback entry, or unmatched Redis command count is a failure for RL stability testing.
- "One game completed" is not enough evidence. The report must include wall time, app duration, per-command timing, trace decision counts, server decision counts, Redis command counts, fallback counts, and per-seat client metrics.
- One-game duration is a guardrail. Human play is slow when players deliberate to win; the protocol path itself is not slow. If one familiar operator can click through the normal game flow within 10 minutes without strategic deliberation, a headless run that exceeds 10 minutes is presumed stuck or desynchronized until the logs prove otherwise.
- A timeout worker must claim the pending prompt before executing fallback. A stale Redis pending snapshot is evidence to re-check state, not permission to append fallback after normal decision acceptance already removed the prompt.

Minimum comparison after every headless live RL run:

- trace `decision_sent` equals server `decision_received`
- trace `decision_ack` equals Redis `decision_submitted`
- rejected/stale/fallback/send-failure/client-error counts are zero, except recovered stale ACKs explicitly paired with bounded unacked resends
- Redis fallback list is empty
- per-seat accepted decisions are plausible for the observed prompt counts; any seat-only buildup is investigated before continuing training
