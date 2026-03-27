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
- At the moment, no separate Claude planning document is present under `PLAN/`; shared architecture specs are the current coordination source

## Planned Work
1. Introduce shared architecture scaffolding under `GPT/` that matches the agreed declaration used by Claude
2. Separate policy specification data from policy interpretation logic
3. Move toward `Spec -> Factory/Creator -> PolicyAsset -> injected runtime policy` composition
4. Extract stable policy concepts from `ai_policy.py` into low-coupling modules with explicit dependencies
5. Preserve runtime behavior by keeping the engine-facing contract stable and refactoring mostly at the injection layer
6. Keep GPT implementation compatible with current simulation, ruleset injection, and analysis flows during transition
7. Add or update tests as the architecture is migrated

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
