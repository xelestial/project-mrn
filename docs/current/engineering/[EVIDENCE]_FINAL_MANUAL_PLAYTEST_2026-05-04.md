# Final Manual Playtest Evidence - 2026-05-04

Status: CURRENT EVIDENCE
Owner: Codex

## Scope

This records the final local manual playtest pass for the non-deployment closure
items:

1. 2-human + 2-AI playtest with the real external-AI worker endpoint
2. 4-human playtest with blocking prompts resolved through the frontend
3. active weather context confirmation from engine/replay through frontend
4. screenshot, replay, and log-audit evidence capture

Deployment-specific external Redis topology proof remains intentionally separate.

## Environment

Services used:

```bash
.venv/bin/python tools/run_external_ai_worker.py \
  --host 127.0.0.1 \
  --port 8011 \
  --worker-id local-priority-bot \
  --policy-mode heuristic_v3_gpt \
  --worker-profile priority_scored \
  --worker-adapter priority_score_v1

MRN_DEBUG_GAME_LOGS=1 .venv/bin/python -m uvicorn apps.server.src.app:app \
  --host 127.0.0.1 \
  --port 9090

VITE_MRN_DEBUG_GAME_LOGS=1 npm run dev -- --host 127.0.0.1 --port 9000
```

External AI smoke:

```bash
.venv/bin/python tools/check_external_ai_endpoint.py \
  --base-url http://127.0.0.1:8011 \
  --require-ready \
  --require-profile priority_scored \
  --require-adapter priority_score_v1 \
  --require-policy-class PriorityScoredPolicy \
  --require-decision-style priority_scored_contract \
  --require-request-type movement \
  --require-request-type purchase_tile
```

Outcome: `OK: external AI endpoint passed smoke checks`.

## Evidence Artifacts

Evidence directory:

`docs/current/engineering/evidence/manual-playtest-2026-05-04/`

Driver summary:

`docs/current/engineering/evidence/manual-playtest-2026-05-04/manual-playtest-driver-result.json`

Screenshots:

- `2h2ai-first-prompt-after-click-seat1.png`
- `2h2ai-seat1-final.png`
- `2h2ai-seat2-final.png`
- `4human-first-prompt-after-click-seat1.png`
- `4human-seat1-final.png`
- `4human-seat2-final.png`
- `4human-seat3-final.png`
- `4human-seat4-final.png`

All screenshots were verified at `1440x900`.

## 1. 2H + 2AI Session

Session: `sess_g9jUne6iNvKi7QC20SJnZYUO`

Result: PASS

Observed metrics:

- frontend UI clicks: `13`
- replay messages: `123`
- rejected decisions: `0`
- external-AI decisions observed: `12`
- `weather_reveal`: `1`
- prompts observed in replay: `5`
- prompts with `weather_context`: `5 / 5`

Replay event counts:

- `draft_pick`: `8`
- `round_order`: `1`
- `turn_start`: `4`
- `trick_window_open`: `4`
- `trick_used`: `2`
- `trick_window_closed`: `4`
- `dice_roll`: `4`
- `player_move`: `4`
- `landing_resolved`: `5`
- `fortune_drawn`: `3`
- `fortune_resolved`: `4`
- `marker_flip`: `7`

Active weather check:

- weather: `길고 긴 겨울`
- effect text: `[종료]를 1칸 앞당기세요`
- frontend evidence: `2h2ai-seat1-final.png` shows the active weather card and the
  common effect while another player's turn is in progress
- replay evidence: every blocking prompt carried `has_weather_context=true`

No duplicate-decision acceptance, stale final-character choice loss, legacy
turn restart, or active-turn marker-flip semantic violation was observed.

## 2. 4-Human Session

Session: `sess_ScoFp5k9ZMmjvro_8eWrTtIr`

Result: PASS

Observed metrics:

- frontend UI clicks: `20`
- replay messages: `70`
- rejected decisions: `0`
- `weather_reveal`: `1`
- prompts observed in replay: `4`
- prompts with `weather_context`: `4 / 4`

Replay event counts:

- `seat_joined`: `4`
- `draft_pick`: `8`
- `round_order`: `1`
- `turn_start`: `3`
- `trick_window_open`: `3`
- `trick_window_closed`: `2`
- `dice_roll`: `2`
- `player_move`: `2`
- `fortune_drawn`: `1`
- `fortune_resolved`: `1`
- `landing_resolved`: `3`
- `mark_queued`: `1`
- `mark_resolved`: `1`
- `action_move`: `1`

Active weather check:

- weather: `맑고 포근한 하루`
- effect text: `모두 주사위 카드를 1장 선택하여 가지세요`
- frontend evidence: `4human-seat1-final.png` shows the active weather card and the
  common effect in the play surface
- replay evidence: every blocking prompt carried `has_weather_context=true`

No rejected prompt continuation, duplicate accepted command, stale prompt resume,
or unresolved draft-final-choice mismatch was observed.

## 3. Debug Log Audit

Initial audit against the new playtest log reported
`draft_choice_missing_from_final_prompt` violations. Investigation showed this
was an audit-tool false positive: real runtime prompts project final-character
choices through `legal_choices` and prompt/surface/view-state/public-context
variants, while the audit script only read the legacy `choices` field.

Fix:

- added `test_debug_log_audit_reads_final_prompt_legal_choices`
- updated `tools/scripts/game_debug_log_audit.py` to collect prompt choice IDs
  from `choices`, `legal_choices`, prompt surface options, nested prompt/view
  state, and `public_context.choice_faces`

Validation:

```bash
.venv/bin/python -m pytest tests/test_game_debug_log_audit_script.py -q
```

Outcome: `5 passed`

```bash
PYTHONPATH=. .venv/bin/python tools/scripts/game_debug_log_audit.py \
  .log/20260504-223005-136500-p4061
```

Outcome:

- `ok: true`
- backend events: `198`
- engine events: `115`
- frontend events: `1402`
- total rows: `1715`
- violations: `0`
- warnings: `0`

## Conclusion

Result: PASS

The final local manual playtest closure is complete for 2H+2AI, 4-human,
evidence documentation, and active-weather context. The active weather identity
and common effect remain visible in frontend screenshots and are present on every
blocking replay prompt inspected in both sessions.
