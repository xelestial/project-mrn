# Redis Runtime UI Playtest Lessons

Status: ACTIVE
Updated: 2026-05-05

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
