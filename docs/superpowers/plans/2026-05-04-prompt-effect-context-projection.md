# Prompt Effect Context Projection Plan

## 1. Goal

Carry the immediate cause/effect context of a decision prompt from backend decision construction through backend view_state and frontend prompt rendering.

This closes the remaining modular boundary where the UI had to infer prompt cause from recent event history. Prompts created by movement, character marks, trick cards, supply/burden handling, or lap rewards should describe their cause in the prompt payload itself.

## 2. Contract

`public_context.effect_context` is authored by the backend decision gateway. Backend `prompt.view_state.active.effect_context` normalizes and projects it. The frontend selector parses it into camelCase and `App` prefers it over event-history fallback context.

Minimum fields:

- `label`: short source label.
- `detail`: readable reason or outcome.
- `attribution`: optional family label.
- `tone`: `move`, `effect`, or `economy`.
- `source`: machine source family.
- `intent`: machine intent.
- `enhanced`: whether the prompt was explicitly enriched.

Optional fields:

- `source_player_id`
- `source_family`
- `source_name`
- `resource_delta`

## 3. Verification

1. Add backend selector coverage that `effect_context` survives prompt view_state projection.
2. Add backend decision gateway coverage for lap reward and trick tile target prompts.
3. Add frontend selector coverage that backend view_state `effect_context` becomes a prompt view model.
4. Run focused Python and frontend tests.

