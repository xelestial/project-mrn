# GPT Architecture Alignment Task

## Task
Align the implementation under `GPT/` with the shared architecture declaration so GPT and Claude can collaborate on the same structural model.

## Scope
- Editable implementation scope: `GPT/`
- Planning and coordination notes: `PLAN/`
- Do not modify `CLAUDE/` from this task
- Also track and absorb compatible ideas from any Claude-side planning notes that appear under `PLAN/`

## Goal
Refactor the current GPT-side architecture toward the common declaration defined by:
- `ARCHITECTURE_REFACTOR_AGREED_SPEC_v1_0.md`
- `ARCHITECTURE_IMPL_GUIDE_v1_0.md`
- `COLLAB_SPEC_v0_3.md`

## Refactor Intent
- Adopt a Unity-style flow:
  - spec
  - creator/factory
  - ScriptableObject-like asset
- Use dependency injection to reduce coupling as much as possible
- Keep the engine stable and avoid invasive engine-side rewrites
- Prefer changing policy injection and composition boundaries over changing engine behavior
- Match Claude's module structure so GPT and Claude can evolve in different directions while remaining structurally compatible
- Preserve cross-compatibility by sharing architecture shape, injection points, naming, and composition contracts

## Current Situation
- Most policy logic is still concentrated in `GPT/ai_policy.py`
- Some concepts have already started to split out into helper modules such as `survival_common.py`, `policy_hooks.py`, and `log_pipeline.py`
- The target shared structure is a modular policy architecture with profile, survival, context, decision, evaluator, asset, and registry layers
- Claude-side planning references now exist under `PLAN/`
  - `CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md`
  - `CLAUDE_MULTI_AGENT_BATTLE_PLAN.md`
- Current GPT-side structure now already includes first-pass shared scaffolding under:
  - `policy/profile`
  - `policy/context`
  - `policy/decision`
  - `policy/evaluator`
  - `policy/asset`
- GPT and Claude can already coexist in one engine process through isolated runtime loading, so the current task is no longer "make coexistence possible" but "reduce the remaining policy-monolith surface while keeping those contracts stable"

## Planned Work
1. Introduce shared architecture scaffolding under `GPT/` that matches the agreed declaration used by Claude
2. Separate policy specification data from policy interpretation logic
3. Move toward `Spec -> Factory/Creator -> PolicyAsset -> injected runtime policy` composition
4. Extract stable policy concepts from `ai_policy.py` into low-coupling modules with explicit dependencies
5. Preserve runtime behavior by keeping the engine-facing contract stable and refactoring mostly at the injection layer
6. Keep GPT implementation compatible with current simulation, ruleset injection, and analysis flows during transition
7. Add or update tests as the architecture is migrated

## Architecture Completion Rule
This document tracks shared-architecture completion for GPT-side runtime structure.

Architecture completion should be judged by:
- engine-facing compatibility
- runtime isolation compatibility with Claude
- policy composition and dependency-injection seams
- shared naming and profile/metadata contracts
- typed context and decision-boundary extraction

Architecture completion should not be blocked by GPT-only analysis tooling such as:
- turn-advantage heuristics
- counterfactual evaluators
- suspicious-move analyzers
- replay-specific analysis overlays

Those belong to GPT-side research and debugging tracks unless they become explicit shared contracts.

## Working Principles
- Behavior-preserving refactor first, strategy retuning second
- Prefer incremental extraction over risky rewrite
- Keep Claude/GPT collaboration in mind by matching names, boundaries, and responsibilities from the shared spec
- Favor DI-friendly seams, registries, and factories over direct hard-coded policy wiring
- Reduce coupling by moving decisions behind injected interfaces instead of engine conditionals
- Preserve engine compatibility by modifying composition roots and policy assembly before touching core runtime loops
- If a Claude-side plan appears in `PLAN/`, reconcile naming, phase order, and module ownership before diverging further
- When Claude-side ideas are better, adopt them as long as they preserve the shared injection contract and engine compatibility
- Record meaningful progress in `PLAN/` when the work direction changes

## Current Execution Focus
- Use `PLAN/CLAUDE_ARCHITECTURE_REFACTOR_PLAN.md` as the naming and phase reference when adding new GPT-side policy seams
- Prefer shared context-style extraction before large policy rewrites so Claude and GPT can consume similar `survival/context` inputs while keeping different heuristics
- Current tactical refactor target:
  - introduce a cleanup-aware common policy context from visible burdens, cash, shard checkpoints, and finite-deck cleanup pressure
  - reuse that context across character evaluation, lap reward choice, and controller-driven leader denial
  - keep engine behavior unchanged and restrict implementation changes to `GPT/`
- Current strategic policy target:
  - add player-level intent memory so adjacent decisions share one plan instead of re-optimizing in isolation
  - treat missing plan continuity as a first-class architecture problem, not just a tuning problem
  - keep engine-facing behavior stable while introducing plan-aware seams inside the GPT policy runtime
- Current extracted seams already in progress:
  - `policy/context/turn_plan.py` now holds player intent and turn-plan context as policy-internal API data
  - `policy/context/survival_context.py` now wraps raw survival dict data into typed policy survival context plus cleanup/action-guard contracts
  - `policy/decision/mark_target.py` now owns public mark-candidate legality filtering
  - `policy/decision/lap_reward.py` now owns plan-aware lap-reward bias that no longer has to live entirely inside `ai_policy.py`
  - `policy/decision/movement.py` now owns intent-aware movement spend penalties for generic land-grab cases
- `policy/decision/purchase.py` now owns reusable reserve-floor logic, v3 purchase-window assessments, and a first purchase-decision result layer
- `policy/decision/trick_usage.py` now owns trick-preservation rules for conditional mobility and shard cards
  - `policy/decision/character_choice.py` now owns shared candidate-evaluation/result packaging for `draft` and `final character`, not just the tie-break choice frame
- Current multi-agent target:
  - allow Claude-strengthened AI and GPT-strengthened AI to coexist as independent player runtimes inside one engine process
  - share only engine-contract model modules such as `config`, `state`, `trick_cards`, `weather_cards`, and `characters`
  - isolate policy-runtime modules such as `ai_policy`, `survival_common`, `policy_hooks`, `policy_groups`, and `policy_mark_utils`
  - prefer runtime-loader isolation over direct cross-repo import shortcuts when composing Claude-vs-GPT battles

## Direction Review

### Review Result
The current direction is still correct.

Why it is correct:
- it preserves the engine-facing `choose_*` contract
- it follows the Claude-side naming direction by creating `profile/context/decision` seams rather than inventing a GPT-only structure
- it reduces coupling by moving policy rules out of `ai_policy.py` into reusable modules
- it keeps GPT-specific heuristics possible without breaking Claude interoperability
- it improves shared-runtime safety before attempting deeper asset/factory migration

### What Has Been Validated
- profile identity is no longer only a mode-string convention; registry-backed profile specs exist
- runtime isolation is already in place for Claude-vs-GPT battle composition
- intent continuity now exists as policy-internal state instead of purely one-shot local scoring
- typed context extraction has begun with:
  - `policy/context/turn_plan.py`
  - `policy/context/survival_context.py`
- decision extraction has begun with:
  - `policy/decision/character_choice.py`
  - `policy/decision/lap_reward.py`
  - `policy/decision/mark_target.py`
  - `policy/decision/movement.py`
  - `policy/decision/trick_usage.py`
  - `policy/decision/purchase.py`
  - `policy/decision/runtime_bridge.py`
- evaluator extraction is now materially in place with:
  - `policy/evaluator/character_scoring.py`
  - `policy/evaluator/runtime_bridge.py`
  - the active v1 character-score path now routes through evaluator-backed structural scoring instead of living only inside `ai_policy.py`
  - the active v2 character-score path now routes its expansion, route, profile, tactical, emergency-risk, post-risk, tail-threat, rent-tail, and `uhsa` tail blocks through evaluator helpers
  - the remaining v3-specific route, cleanup-anchor, shard-checkpoint, and safe-expansion meta blocks now also route through evaluator helpers on the live scoring path
  - leader-emergency, cash-dry, escape-liquidity, burden-liquidity, mark-risk, and standardized rent-tail packaging are now emitted from evaluator helpers on the live scoring path
- the active v1/v2 target-scoring paths now also route through the runtime bridge instead of keeping their scoring bodies only in `ai_policy.py`
- active decision paths such as purchase, lap reward, trick use, mark target, hidden trick, specific trick reward, coin placement, active flip, burden exchange, and doctrine relief now increasingly route through `policy/decision/runtime_bridge.py` instead of keeping their live orchestration only inside `ai_policy.py`
- the remaining active monolith decision paths such as movement, draft-card choice, final-character choice, and geo bonus now also route through `policy/decision/runtime_bridge.py`, so the live `choose_*` surface is largely bridge-backed even though dormant legacy bodies still remain in `ai_policy.py`
- asset/factory extraction has begun with:
  - `policy/asset/spec.py`
  - `policy/factory.py`
  - arena lineup normalization and default fill now route through the factory bridge instead of living only inside `ArenaPolicy`
  - heuristic profile-mode canonicalization and lap-mode normalization now also route through the factory bridge before `HeuristicPolicy` is constructed
  - GPT entrypoints now increasingly consume direct factory helpers such as `create_heuristic_policy_from_modes(...)` instead of rebuilding heuristic assets inline
- character-choice evaluation metadata now feeds debug output directly, so draft/final-character debug no longer needs a second survival-advice pass just to reconstruct severity details
- part of `_character_score_breakdown()` now routes through evaluator helpers instead of living entirely inside `ai_policy.py`
- `ArenaPolicy` now creates per-player heuristic policies through `PolicyFactory`, so a real composition bridge exists even though it is still minimal
- GPT entrypoints such as `main.py`, `simulate_with_logs.py`, and `debug_cli.py` now also consume the factory bridge instead of instantiating heuristic policies directly

This means the current structure is now materially closer to the shared target than the original plan assumed.
The GPT runtime already has a real `policy/profile + policy/context + policy/decision` spine, even though `ai_policy.py` still remains too large.

### What Is Still Wrong Or Incomplete
- `ai_policy.py` is still the orchestration center, but character scoring is now increasingly composed from evaluator helpers instead of monolithic inline blocks
- `draft` and `final character` now share both a decision-layer choice frame and candidate-evaluation packaging, but their raw scoring heuristics still live mostly inside `ai_policy.py`
- `draft` and `final character` now also build through a `NamedCharacterChoicePolicy` config object, so `ai_policy.py` no longer has to inline the full callable bundle for those evaluation paths
- `draft` and `final character` now build that config through a shared decision helper, so `ai_policy.py` no longer constructs the named-choice policy object directly
- `draft` and `final character` now also execute candidate evaluation and debug-summary packaging through a shared decision helper, so `ai_policy.py` no longer has to pair those two steps manually
- smaller selection paths such as specific trick rewards are now also starting to route through shared scored-choice helpers instead of open-coding `max(...)` plus manual debug score maps
- smaller ranking-based selection paths such as coin placement are now also starting to route through shared ranked-choice helpers instead of open-coding `max(...)` directly
- smaller ranking-based selection paths such as v2 geo-bonus selection are now also starting to route through shared ranked-choice helpers instead of open-coding tuple `max(...)`
- purchase debug payloads now also start routing through shared purchase-decision helpers instead of being rebuilt inline inside `ai_policy.py`
- purchase decision callsites now also start routing final yes/no outcomes through shared purchase-decision helpers instead of keeping the final veto logic entirely inline
- support-style choices such as doctrine-relief targeting and burden-exchange gating are now also starting to route through shared decision helpers instead of staying as one-off inline routines
- support-style choices such as geo-bonus final selection now also route through shared decision helpers instead of keeping all final cash/shard/coin branching inline
- smaller ranking-based selection paths such as hidden-trick hiding and active-flip final card selection now also route through shared ranked-choice helpers instead of open-coded `max(...)`
- medium-complexity scored selection paths such as trick-use are now also starting to route through shared scored-choice helpers instead of hand-maintaining `best / best_score / details` loops
- purchase base-benefit packaging now also routes through a shared helper instead of rebuilding that structural score inline inside `choose_purchase_tile(...)`
- mark-target debug payload packaging now also routes through a shared decision helper instead of rebuilding the payload shape inline at every exit path
- mark-target public score/probability evaluation now also routes through a shared decision helper instead of open-coding the candidate loop and distribution packaging inside `ai_policy.py`
- mark-target weighted resolution now also routes through a shared decision helper instead of assembling score evaluation, weighted choice, and debug packaging separately inside `ai_policy.py`
- mark-target empty/random fallback branches now also route through shared decision helpers instead of rebuilding those debug payloads inline inside `ai_policy.py`
- `choose_mark_target(...)` now also uses those helper-backed empty/random/weighted resolution paths on its live branch, so the active public-mark flow no longer open-codes those packaging steps inside `ai_policy.py`
- v3 purchase-window flag derivation now also reuses shared purchase helpers inside `policy/decision/purchase.py` instead of duplicating the low-cost-T3/growth-window conditions in multiple places
- active-flip random/final debug payload packaging now also routes through a shared decision helper instead of keeping that output shape inline inside `ai_policy.py`
- the main `choose_purchase_tile(...)` v3 pre-scoring path now also routes its low-cost-T3, growth-window, burden drag, and early token-window veto through shared purchase helpers instead of rebuilding those calculations inline
- character-role/package identification now has a separate helper layer outside `ai_policy.py`, so future refactors can replace encoding-fragile name comparisons with card-face/card-number trait lookups instead of touching mojibake literals in-place
- exact-face trait helpers now also exist for `어사`, `탐관오리`, `자객`, `산적`, `파발꾼`, and `아전`, so the remaining live-path direct face checks can route through stable helper predicates instead of inline name comparisons
- the main `choose_purchase_tile(...)` baksu-exception path now also computes its effective override from helper-backed character traits, so the final decision no longer depends only on mojibake name comparisons for that critical survival exception
- purchase trait-backed wrapper helpers now also exist for v3 purchase-window assessment and final purchase-decision resolution, so the live purchase path can route through card-face-aware logic without patching the most encoding-fragile legacy helpers in-place
- the main purchase path no longer rebuilds a second inline `PurchaseDecisionResult` after helper evaluation, so `choose_purchase_tile(...)` now trusts the shared purchase-decision result more directly and stays closer to an orchestration shell
- active-flip money-drain relief logic now also routes through helper-backed character-trait checks instead of depending directly on mojibake-name set membership in the flip path
- active money-drain pressure estimation now also routes through helper-backed character-trait checks instead of directly consulting mojibake-name set membership in the opponent scan path
- low-cash character role buckets are now also re-declared from helper-backed character-trait functions, so shared scoring paths can consume card-face-based role sets without depending on the original mojibake literal definitions as the source of truth
- survival-adjustment low-cash routing now also uses helper-backed role checks for escape / income / controller / disruptor paths instead of consulting the role bucket sets directly at every callsite
- dedicated trait helpers now also exist for growth / cleanup / swindler faces, so future survival-advice and purchase cleanup callsites can move off direct mojibake-name checks without inventing new inline card-face logic
- `draft` / `final character` now route their survival-policy advice and survival-adjustment hooks through trait-backed wrapper methods, so the live character-choice path no longer depends on the older mojibake-heavy survival helper bodies even though those legacy bodies still remain in the file
- `choose_hidden_trick_card(...)` now also routes through a dedicated hidden-trick scoring helper before reaching the older inline scoring loop, so the live hidden-card path no longer depends on direct mojibake-name comparisons in that routine
- `choose_lap_reward(...)` now routes the live `heuristic_v3_gpt` path through a dedicated trait-backed helper in `policy/decision/lap_reward.py`, so the main v3 lap-reward scoring path no longer depends on the older mojibake-heavy inline branch even though that legacy branch still remains in the file
- `choose_lap_reward(...)` now also routes the `balanced` fallback path through a small shared helper, so lap-reward selection is increasingly centered in the decision layer rather than open-coded inside `ai_policy.py`
- `choose_lap_reward(...)` now also routes the non-v2 fallback path through the same shared basic helper, so all non-v2 lap-reward live paths now pass through decision-layer helpers before the legacy inline body
- the active balanced/basic live branches of `choose_lap_reward(...)` now also execute through `evaluate_basic_lap_reward(...)`, so those fallback reward modes no longer open-code their final resource preference ladder inside `ai_policy.py`
- `choose_coin_placement_tile(...)` now routes through a dedicated decision helper instead of open-coding token-window ranking inline inside `ai_policy.py`
- `choose_active_flip_card(...)` now routes its random/scored resolution and debug payload packaging through shared decision helpers instead of open-coding those end-of-path selection steps inside `ai_policy.py`
- the current live branch of `choose_active_flip_card(...)` now also executes through those shared random/scored resolution helpers, so the active marker-flip path no longer hand-builds its final debug payload inside `ai_policy.py`
- `choose_specific_trick_reward(...)` now routes its scored resolution and debug payload packaging through shared decision helpers instead of open-coding the end-of-path selection/debug steps inside `ai_policy.py`
- `choose_purchase_tile(...)` now routes structural block-count and immediate-win checks through shared purchase helpers instead of open-coding those bookkeeping steps inline inside `ai_policy.py`
- `choose_purchase_tile(...)` now also routes its live v3 purchase-benefit preparation through a trait-backed helper, so the main v3 purchase path relies less on inline benefit-adjustment assembly inside `ai_policy.py`
- `choose_purchase_tile(...)` now also routes early-exit debug payload packaging through shared purchase helpers instead of rebuilding those small failure payloads inline inside `ai_policy.py`
- `choose_active_flip_card(...)` now also routes chosen-face resolution through the shared active-flip helper instead of precomputing that payload-specific field inline before helper resolution
- `choose_trick_to_use(...)` now also routes its final debug payload packaging through a shared trick-usage helper instead of rebuilding that score/urgency payload inline inside `ai_policy.py`
- `choose_trick_to_use(...)` now also routes its scored choice resolution through a shared trick-usage helper instead of calling `run_scored_choice(...)` directly inside `ai_policy.py`
- `choose_purchase_tile(...)` now also routes its immediate-win purchase-result packaging through a shared purchase helper instead of rebuilding that trivial success result inline inside `ai_policy.py`
- `choose_draft_card(...)` and `choose_final_character(...)` now also route their final debug payload packaging through a shared character-choice helper instead of rebuilding those large summary dicts inline inside `ai_policy.py`
- `choose_draft_card(...)` and `choose_final_character(...)` now also route their uniform-random fallback debug payloads through the same character-choice helper layer instead of rebuilding those trivial random payloads inline inside `ai_policy.py`
- movement generic land-spend penalties now also route through a trait-backed helper (`is_gakju(...)`) instead of comparing the innkeeper face inline inside the movement decision module
- trick-preservation rules now also route their builder / route-runner / shard-hunter checks through card-face-backed character traits instead of direct mojibake-name comparisons inside `policy/decision/trick_usage.py`
- the remaining live-path direct character-name comparisons inside `ai_policy.py` have now been reduced to weather/fortune-name constants and a few non-trait string tables; player-face checks on the hot decision paths now route through helper-backed predicates
- weather / fortune cleanup-name tables and weather-character synergy rules now also have a dedicated helper module under `policy/environment_traits.py`, and live-path weather adjustment plus cleanup-deck counting now route through late helper-backed overrides instead of keeping those string-heavy tables only inside `ai_policy.py`
- the lap-reward bundle combinatorics now also route through `policy/decision/lap_reward.py`, so `ai_policy.py` no longer has to keep the full bundle search loop inline when converting per-resource scores into a final reward package
- escape-package / marker-package live paths now also route through trait-backed late overrides, so the active rescue-vs-marker decision path no longer depends on the older mojibake-heavy package name tables
- visible burden counting and specific trick-reward live paths now also route through card metadata (`TrickCard.is_burden`) plus shared trick-reward helpers, further reducing direct burden-name comparisons on active decision paths
- escape-package seeking and distress-marker bonus live paths now also route through shared support-choice helpers instead of keeping that rescue-vs-marker math only inside `ai_policy.py`
- visible burden counting now also routes through a shared support-choice helper instead of open-coding burden summation in the late live override
- specific trick-reward live path now also routes its final choice plus debug payload packaging through a shared `resolve_trick_reward_choice_run(...)` helper instead of assembling those two steps separately inside `ai_policy.py`
- hidden-trick live path now also routes its final choice plus debug payload packaging through a shared `resolve_hidden_trick_choice_run(...)` helper instead of re-resolving the chosen card and payload shape inside `ai_policy.py`
- evaluator extraction now owns the active v1/v2/v3 character-scoring path, even though legacy inline scoring bodies still remain in `ai_policy.py` as dormant historical implementations
- evaluator extraction now also owns the active v1/v2 target-scoring path through the runtime bridge, so `ai_policy.py` no longer needs to keep live target-score bodies either
- v2 post-risk scoring such as cash-dry reserve pressure now also routes through evaluator helpers instead of staying inline at the tail of `_character_score_breakdown_v2()`
- v2 tail-threat scoring such as public mark-risk penalty now also routes through evaluator helpers instead of staying inline at the tail of `_character_score_breakdown_v2()`
- v2 rent-tail packaging such as standardized rent-pressure reason emission now also routes through evaluator helpers instead of staying inline at the tail of `_character_score_breakdown_v2()`
- a dedicated `uhsa` tail helper now exists in the evaluator layer as groundwork for extracting the remaining muroe-block penalty once the encoding-fragile callsite is patched safely
- `PolicyAsset` / `PolicyFactory` composition now exists as a real bridge, and both arena/default normalization and heuristic-mode normalization moved there; GPT entrypoints also started using direct factory helpers; however, it still does not yet own the full policy assembly story
- battle composition now also has a first asset/factory bridge through `MultiAgentBattleAsset` and factory-created dispatcher assembly, so battle wiring no longer needs to open-code per-player fallback filling
- `PolicyFactory` now also exposes a runtime-level dispatcher for heuristic-vs-arena creation, so entrypoints can assemble policies through one bridge instead of open-coding that split
- typed contexts are present and expanding, but are not yet the only way decisions consume survival and turn-planning data
- purchase now has a real decision-result layer and its dead duplicate branch has been removed, but the surrounding orchestration still lives in `ai_policy.py`
- purchase now also rebuilds reserve-floor and debug payload data through shared purchase helpers, so `ai_policy.py` no longer has to inline those support calculations end-to-end
- purchase now also lets shared purchase helpers produce the final decision result for the main `choose_purchase_tile` path, even though some pre-scoring setup still remains inline
- burden-exchange-on-supply now also reuses typed survival-context + shared purchase reserve-floor logic instead of maintaining a separate cleanup-floor formula inline
- geo-bonus evaluation now reads more of its survival state from `PolicySurvivalContext` instead of re-reading raw survival dict keys one by one
- active-flip evaluation now also reads its controller/distress/survival summary from `PolicySurvivalContext` instead of only raw survival dict lookups
- `draft` / `final character` now execute through shared evaluation helpers and their dead duplicate fallback blocks inside `ai_policy.py` have been removed
- a late overriding `choose_hidden_trick_card(...)` method that used to null out the helper-backed path now also routes through the shared hidden-trick resolver, and that live regression is covered by tests
- movement decision now also routes its final single-card / double-card best-choice loop through a shared movement resolver instead of open-coding the candidate sweep inside `ai_policy.py`
- v2 lap-reward profile logic now also has a shared helper layer for `growth`, `avoid_control`, `aggressive`, and `token_opt`, and those live branches no longer need to inline their score adjustments inside `ai_policy.py`
- v2 lap-reward `control` logic now also routes most of its cash/coin pressure adjustments through the same profile helper, with only a small mojibake-heavy controller-role shard bonus still left inline at the callsite
- lap-reward score normalization and preferred-resource resolution now also route through a shared helper instead of rebuilding reward-unit packaging inline inside `ai_policy.py`
- purchase decision now also routes its large trait-heavy argument pack through a shared `TraitPurchaseDecisionInputs` wrapper instead of open-coding that full helper call inline inside `ai_policy.py`
- purchase debug payload assembly now also routes through a shared `build_purchase_debug_context(...)` helper instead of rebuilding the full `PurchaseDebugContext(...)` object inline inside `ai_policy.py`
- the active `choose_purchase_tile(...)` live branch now also assembles its benefit/window/result flow through shared purchase helpers end-to-end, so the remaining purchase work is mostly legacy scoring cleanup rather than helper/wrapper extraction
- a late overriding `choose_lap_reward(...)` live branch now also routes the active `heuristic_v3_gpt` reward scoring through `policy/decision/lap_reward.py`, so the remaining lap-reward work is mostly legacy inline cleanup rather than helper/wrapper extraction
- helper/wrapper extraction for the live decision paths is now effectively complete
- evaluator extraction for the live character-scoring paths is now also effectively complete
- the next major refactor axis is legacy-body cleanup / final monolith reduction, since the remaining large problem is now mostly dormant historical bodies inside `ai_policy.py` rather than still-live non-bridged `choose_*` paths

### Updated Interpretation
This plan has moved from:
- "create the first compatible structure"

to:
- "continue shrinking the monolith while preserving the already-working shared contracts"

## Out Of Scope For Architecture Completion
The following may continue independently and do not prevent this plan from eventually becoming complete:
- `PLAN/GPT_TURN_ADVANTAGE_ANALYSIS_PLAN.md` beyond already-finished shared parser groundwork
- GPT-only post-game strategy analysis reports under `result/`
- GPT-only suspicious-step tagging and evaluator heuristics
- GPT-only replay overlays that consume architecture outputs without defining engine or wrapper contracts

## Intent Memory Direction

### Problem
The current GPT policy mostly re-evaluates each `choose_*` call from the current `GameState`.
That means:
- state persists, but intent does not
- character choice, trick use, movement, purchase, mark, and lap reward can optimize different local heuristics
- one player can look like a different pilot every decision

### Required Change
Add a lightweight player-scoped plan layer inside the GPT policy runtime.

Initial target artifacts:
- `PlayerIntentState`
- `TurnPlanContext`
- plan-aware helpers used by `choose_final_character`, `choose_trick_to_use`, `choose_movement`, `choose_purchase_tile`, `choose_lap_reward`, and `choose_mark_target`

### Initial Plan Categories
- `lap_engine`
- `survival_recovery`
- `controller_disrupt`
- `land_grab`
- `leader_denial`

### Minimum Stored Signals
- current plan key
- plan start round
- current target if any
- resource intent such as `cash_first`, `shard_checkpoint`, `card_preserve`
- recent character-selection reason summary

### Design Rule
- do not move planning into the engine
- keep plan state inside GPT policy composition
- allow plan state to expire or recompute when the board changes materially

## Remaining Architecture Priorities
1. Continue converting direct `survival_ctx` dict reads into `PolicySurvivalContext` consumption.
2. Reduce `HeuristicPolicy` toward an orchestration shell instead of a rule monolith.
3. Pull more `draft` / `final character` scoring logic out of `ai_policy.py` now that shared evaluation packaging and first evaluator splits are authoritative.
4. Widen the `PolicyFactory` / `PolicyAsset` bridge beyond lineup normalization, runtime policy dispatch, battle-dispatch assembly, and per-policy creation.
5. Keep metadata and wrapper contracts stable while those extractions continue.
Legacy body cleanup status:
- Active `choose_*` live paths now delegate through `policy/decision/runtime_bridge.py`.
- Shadowed legacy `choose_*` bodies inside `GPT/ai_policy.py` have been neutralized with explicit dead-body guards where they were no longer authoritative.
- Helper/wrapper, scoring/evaluator, runtime-bridge, and legacy-body cleanup work are complete enough to treat the refactor as finished.
- Remaining work in `GPT/ai_policy.py` is optional polish only:
  - physical deletion of dormant dead bodies
  - additional file-size reduction
  - import ordering / cosmetic cleanup

Refactor completion summary:
- Live decision paths are bridge-backed.
- Live scoring paths are evaluator-backed.
- Dormant monolithic bodies are explicitly marked dead where needed.
- Current work after this point is maintenance polish, not architecture-blocking refactor work.
