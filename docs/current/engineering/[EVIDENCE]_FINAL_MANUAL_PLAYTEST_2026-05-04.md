# Final Manual Playtest Evidence

Status: ACTIVE
Updated: 2026-05-05

## 1. Scope

This file records the manual-playtest checkpoints that remain useful for the current module runtime.

## 2. Covered Flows

- first turn executes from the scheduled player turn
- draft final choice persists through the final decision
- trick follow-up prompts resume inside the trick sequence
- mark targeting does not restart after trick follow-up
- fortune follow-up movement stays inside the action sequence
- round-end card flip happens after all player turn work completes
- duplicate frontend decisions do not advance the engine twice
- simultaneous resupply waits for all required players

## 3. Required Runtime Signals

- prompt continuation fields are present on every decision prompt
- simultaneous prompts include batch fields and missing-player state
- stream events carry the owning runtime module
- view recovery emits `view_state_restored`

## 4. Follow-Up Verification

Manual playtest remains the final confidence check after automated runtime/server/web tests pass.
