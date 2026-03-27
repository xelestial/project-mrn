# GPT Turn Advantage Analysis Plan

## Goal
Add a non-invasive analysis pipeline that can answer two questions from raw logs:

1. At each turn, who was ahead and by how much?
2. At each decision point, was the chosen action likely the best available action?

This work must preserve the existing engine contract and keep analysis outside the main runtime loop as much as possible.

## Why
Current summaries tell us who won and broad strategy patterns, but they do not tell us:
- when momentum changed
- which turn created the swing
- whether a policy made the best local choice from the information it had

To answer that, we need a stable pipeline:
- raw action log
- turn parser
- advantage scorer
- decision-point evaluator
- counterfactual simulator

## Architecture

### Phase 1. Raw Log to TurnBundle
Input:
- `action_log`

Output:
- `TurnBundle`

Required fields:
- `round_index`
- `turn_index`
- `player`
- `character`
- `move_roll`
- `landing_type`
- `semantic_events`
- `runtime_events`
- `resource_deltas`
- `human_summary`

Rule:
- engine remains unchanged except for future optional log-field enrichment
- parser reconstructs turns from existing rows

### Phase 2. TurnBundle to AdvantageSnapshot
Input:
- ordered `TurnBundle` list

Output:
- per-turn player advantage scores

Minimum tracked state:
- cash
- tiles
- placed score coins
- hand coins
- shards
- laps completed
- alive status

Minimum derived outputs:
- per-player heuristic advantage score
- seat rank after each turn
- leader id after each turn
- score margin to leader

Rule:
- this stage uses only visible state and deterministic reconstructed state
- no hidden-info speculation yet

### Phase 3. DecisionPoint Extraction
Input:
- `TurnBundle`
- embedded policy decision rows

Output:
- normalized decision records

Target decision types:
- draft
- final character
- trick use
- movement
- purchase
- lap reward
- mark target
- active flip

Required fields:
- decision name
- acting player
- turn index
- observed choice
- visible context summary

### Phase 4. Counterfactual Evaluation
Input:
- one `DecisionPoint`
- reconstructed turn state
- candidate alternatives

Output:
- expected local value of each candidate
- best candidate
- actual-minus-best gap

Evaluation modes:
- fast heuristic evaluator
- bounded forward simulation

Recommended rollout horizons:
- `1 turn`
- `2 turns`
- `to end` only for special offline studies

Rule:
- start with heuristic local evaluation
- add bounded simulation only to the decision types that matter most

## Data Contracts

### TurnBundle
- parser product
- one row per completed player turn
- no policy judgment yet

### AdvantageSnapshot
- turn-level ranking state
- one record per player per turn
- should be serializable to JSON/CSV

### DecisionPoint
- one decision event at one turn
- references the acting player and visible state

### CounterfactualReport
- records actual choice
- candidate list
- best alternative
- estimated delta

## Required Log Improvements
The current logs are already useful, but future best-choice analysis improves if we also log:
- decision candidate set when available
- explicit turn-start snapshot
- explicit turn-end snapshot
- clearer action result labels for lap reward, purchase, mark, and movement
- optionally an analyzable RNG/deck state marker for offline replay

These are optional for Phase 1 and Phase 2.

## Initial GPT Implementation Scope
Start now with:
- `action_log_parser.py`
- `turn_advantage.py`
- tests for parser and basic advantage ranking

Do not start yet with:
- engine modifications
- exhaustive best-choice simulation
- hidden-information inference

## Success Criteria
Phase 1 is successful if:
- raw action logs can be converted into stable `TurnBundle` rows
- sample games can be narrated per turn without manual inspection

Phase 2 is successful if:
- each turn can produce a ranked view of who is ahead
- momentum shifts can be identified automatically

Phase 3 and 4 are successful if:
- we can point to a concrete turn and say the policy had a stronger available choice
- the analysis works for both Claude and GPT lineups

## Immediate Next Actions
1. Implement `GPT/action_log_parser.py`.
2. Implement `GPT/turn_advantage.py`.
3. Add parser tests on synthetic action logs.
4. Add one real-log smoke path that parses an existing game log.
