# [COMPLETE] GPT Phase 4 Human Play Baseline

Status: `COMPLETE`
Date: `2026-03-28`

## Scope
Phase 4 baseline from `PLAN/GPT_ONLINE_STYLE_REPLAY_VISUALIZATION_PLAN.md`:
- prompt schema
- prompt file channel
- human decision adapter
- playable runtime entry point
- live spectator + prompt bundle for a human seat

## Implemented Files
- `GPT/viewer/prompting.py`
- `GPT/viewer/human_adapter.py`
- `GPT/viewer/playable_runtime.py`
- `GPT/run_live_playable.py`
- `GPT/test_human_prompt_runtime.py`

## Delivered Capabilities
- engine-facing decisions can now open a `RuntimePrompt`
- prompt state is materialized to `prompt_state.json`
- prompt open/close history is materialized to `prompt_history.jsonl`
- non-human seats still delegate to AI policy
- human seats can answer non-trick prompts through the response-provider interface
- a live playable bundle can be produced alongside the live spectator bundle

## Included Prompt Families In First Baseline
- movement
- purchase decision
- draft choice
- final character choice
- lap reward
- mark target
- coin placement
- doctrine relief
- geo bonus
- active flip
- burden exchange

## Explicitly Deferred
- trick-family prompts
- browser-side prompt submission
- websocket prompt transport
- fully graphical input widgets

## Validation
- `python -m pytest -q GPT/test_human_prompt_runtime.py GPT/test_live_spectator.py GPT/test_replay_viewer.py GPT/test_visual_runtime_substrate.py`
- scripted playable smoke through `viewer.playable_runtime.run_playable_seed(...)`

## Notes
- this milestone proves prompt round-trip through shared prompt schema
- the current response bridge is CLI/scripted, not browser-native yet
- the next phase should focus on browser-side response submission and prompt transport wiring
