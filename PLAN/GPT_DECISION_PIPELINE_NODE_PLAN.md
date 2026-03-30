# GPT Decision Pipeline Node Plan

Status: `COMPLETE`
Role: `canonical plan for rewriting GPT AI decisions into reusable node/pipeline form`

## Current Implementation Snapshot

### Completed In This Pass
- added shared `DetectorHit` / `DecisionTrace` substrate in [GPT/policy/pipeline_trace.py](/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/policy/pipeline_trace.py)
- wired canonical trace payloads into:
  - purchase decision runtime
  - movement decision runtime
  - lap reward runtime
  - character draft runtime
  - final character runtime
  - mark target runtime
  - doctrine relief runtime
  - geo bonus runtime
  - coin placement runtime
  - active flip runtime
  - burden exchange runtime
  - trick-use runtime
  - hidden-trick selection runtime
  - trick reward runtime
- reattached movement intent adjustment to the modular runtime path so card-preserve / lap-engine bias is no longer lost after bridge delegation
- added regression coverage for:
  - purchase trace embedding
  - movement trace emission
  - lap reward trace emission
  - character / support-choice trace emission

### What This Means
- we now have a reusable pipeline-trace substrate across the full first-pass non-trick decision surface
- detector hits are structured instead of living only as ad-hoc booleans in debug payloads
- replay/live/debug tooling can now consume a common `source -> features -> detector_hits -> effects -> final_choice` shape
- batch simulation now exports those decision rows into `ai_decisions.jsonl`, so AI tuning can use offline decision logs without scraping full action logs
- offline analysis now has [GPT/analyze_ai_decisions.py](/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/analyze_ai_decisions.py), which summarizes detector hits, final choices, and decision-family counts directly from `ai_decisions.jsonl`
- movement traces now emit richer no-card / tempo detectors (`hold_cards_default`, `single_card_tempo_pick`) so the pipeline explains both aggressive and conservative movement lines
- purchase traces now emit `safe_growth_beats_token_wait` when `v3_gpt` deliberately buys a safe growth tile instead of over-waiting for a modest score-coin window

### Completion Note
- the original first-pass non-trick scope is complete
- the follow-through trick-family scope is now also traced through the same substrate
- the optional visualization / introspection layer is now available through Mermaid export in [GPT/analyze_ai_decisions.py](/Users/SIL-EDITOR/Desktop/Workspace/project-mrn/GPT/analyze_ai_decisions.py)
- current plan scope is complete; future work is optional UI/tooling polish rather than missing pipeline coverage

## Goal
Rewrite the existing GPT AI decision logic into a pipeline-oriented structure that is:

- explainable
- testable
- reusable across live play and replay analysis
- compatible with future visual node-style debugging

This plan now covers all major GPT AI runtime decisions exposed through the current policy bridge.

## Scope Freeze

### Included In First Implementation
- character draft choice
- final character choice
- movement choice
- purchase choice
- lap reward choice
- mark target choice
- doctrine relief choice
- geo bonus choice
- coin placement choice
- active flip choice
- burden exchange choice

### Trick-Family Follow-Through
- trick-use decision pipeline is now traced
- hidden trick choice pipeline is now traced
- trick reward choice pipeline is now traced
- anytime trick timing remains a separate runtime/prompt concern, but its choice outputs now land in the common trace schema

## Why A Pipeline Rewrite Is Worth Doing
The current runtime is already partly decomposed, but it is still hard to answer:

- what features were read
- which rule fired
- how much score changed
- which veto or override decided the result

The pipeline rewrite should make each decision traceable as:

`source -> features -> patterns -> effects -> final choice`

## Architectural Direction

### 1. Source Layer
Raw state inputs converted into normalized decision context.

Examples:
- actor state
- board state
- turn order / marker order
- public opponent state
- current round weather / F / supply status
- current plan / survival context
- candidate-specific raw facts

### 2. Feature Layer
Reusable computed signals that can be shared by multiple decisions.

Examples:
- position and route features
- tile profit/loss features
- lap/F probability features
- cleanup/burden threat features
- controller / mark threat features
- monopoly / takeover opportunity features
- liquidity / reserve features

### 3. Pattern Layer
Named detectors over feature outputs.

Examples:
- `adv_gakju_lap_window`
- `adv_safe_growth_buy`
- `stupid_generic_two_card_land_grab`
- `stupid_help_run_no_forward_encounter`
- `stupid_relic_collector_no_shard_window`

The pattern layer should return structured hits rather than directly changing scores.

### 4. Effect Layer
Transforms pattern hits into policy effects.

Supported effect types:
- hard veto
- soft penalty
- soft bonus
- exception override
- forced preference ordering

### 5. Final Decision Layer
Combines:
- base evaluator score
- effect adjustments
- tie-breaks
- final debug trace

## Function Shape
Prefer pure-function nodes over stateful classes.

Recommended style:

```python
ctx = build_decision_context(...)
features = build_purchase_features(ctx)
hits = run_purchase_detectors(features)
effect = resolve_purchase_effects(hits, ctx)
result = finalize_purchase_choice(ctx, features, effect)
```

DI should apply at:
- registry level
- context builder level
- effect resolver level

DI should not be overused for:
- tiny feature functions
- tiny detectors
- static value objects

## Recommended Data Types

### DecisionContext
The normalized input for one actor, one decision, one candidate set.

Contains:
- actor id / actor character
- decision type
- state snapshots needed for that decision
- public board view
- survival context
- turn plan
- candidate list

### DecisionFeatures
Decision-specific derived values.

Examples:
- `expected_tile_value`
- `cleanup_pressure`
- `token_window_value`
- `lap_window_score`
- `forward_encounter_exists`
- `reserve_gap`

### DetectorHit
Structured detector result.

Recommended shape:
- `key`
- `kind`
- `severity`
- `confidence`
- `reason`
- `tags`

### EffectResolution
Effect-layer output.

Examples:
- vetoed candidates
- additive score changes
- preferred candidate ids
- debug reasons

## Pipeline Families

### A. Board/Route Pipelines
Reusable across movement, purchase, lap reward, geo bonus.

Needed sub-pipelines:
- current position pipeline
- reachable tile pipeline
- tile value pipeline
- tile danger pipeline
- start-cross / lap window pipeline
- F landing pipeline

### B. Survival Pipelines
Reusable across character, movement, purchase, doctrine, lap reward.

Needed sub-pipelines:
- burden threat pipeline
- cleanup threat pipeline
- rent lethality pipeline
- cash reserve pipeline
- money distress pipeline

### C. Control/Interaction Pipelines
Reusable across mark target, character choice, movement, lap reward.

Needed sub-pipelines:
- mark exposure pipeline
- controller threat pipeline
- visible opponent leverage pipeline
- denial opportunity pipeline

### D. Character Pipelines
Character-specific composition over common pipelines.

Examples:
- `객주`: lap engine, revisit value, coin value, board-end mobility
- `박수`: burden pressure, shard checkpoints, fallback mark value
- `사기꾼`: takeover value, hostile landing conversion value
- `교리 감독관`: burden distress rescue value

### E. Trick Pipelines
Deferred until manual audit.

Later this should include:
- trick capability metadata
- timing window detectors
- effect-family grouping
- held-anytime vs regular phase separation

## Decision Mapping

### Draft / Final Character
Base evaluator:
- character scoring evaluator

Pipeline additions:
- survival profile pipeline
- control pressure pipeline
- route opportunity pipeline
- plan alignment pipeline

### Movement
Base evaluator:
- reachable destination score

Pipeline additions:
- tile value pipeline
- tile danger pipeline
- lap/F window pipeline
- character movement synergy pipeline

### Purchase
Base evaluator:
- immediate board gain

Pipeline additions:
- reserve / cleanup pipeline
- monopoly / denial pipeline
- token window pipeline
- survival override pipeline

### Lap Reward
Base evaluator:
- cash / shard / coin score

Pipeline additions:
- survival need pipeline
- shard checkpoint pipeline
- coin conversion pipeline
- character lap synergy pipeline

### Mark Target
Base evaluator:
- public probability / harm value

Pipeline additions:
- control pressure pipeline
- impossible-target filter
- public confidence pipeline

### Doctrine Relief
Base evaluator:
- target distress

Pipeline additions:
- burden threat pipeline
- cleanup lethality pipeline
- cash rescue urgency pipeline

### Geo Bonus
Base evaluator:
- cash / shard / coin need

Pipeline additions:
- survival reserve pipeline
- shard checkpoint pipeline
- coin engine pipeline

## Debugging Goal
Every final decision should be explainable as:

1. base score
2. feature outputs
3. detector hits
4. effect adjustments
5. final ranking

This must be capturable in replay analysis later.

## Implementation Order

### Phase 1
- define shared pipeline dataclasses
- build source/context builders
- build board/route pipelines
- build survival pipelines
- migrate purchase
- migrate movement
- migrate lap reward

### Phase 2
- migrate draft/final character
- migrate mark target
- migrate doctrine relief
- migrate geo bonus
- migrate coin placement / active flip / burden exchange

### Phase 3
- audit trick system
- only after audit, add trick-specific pipeline family

## Success Criteria
- at least purchase, movement, and lap reward share reusable feature pipelines
- detector hits are separately inspectable from final score
- active runtime uses the new pipeline path
- decision traces become renderable in a future node-style debug view
- trick pipelines remain deferred until their audit is complete
