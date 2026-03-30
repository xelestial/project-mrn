# [DECISION] React UI Stack Strategy (`2026-03-30`)

## Decision

For v1 online runtime UI, we keep:

- React + TypeScript
- plain CSS (component-scoped class naming convention)
- no utility-first framework dependency in this phase

## Why

1. Current UI scope is still contract/flow stabilization, not visual-system expansion.
2. Additional utility/framework migration now increases regression risk in prompt/timeline/board behavior.
3. Existing style baseline can be evolved incrementally with predictable diffs and low tooling overhead.
4. Future Unity frontend migration path does not benefit from introducing extra CSS framework coupling now.

## Guardrails

- Prefer feature-local class blocks by component area.
- Keep shared design tokens in one place (colors/spacing/typography constants).
- If theme/system complexity crosses current baseline, open v2 decision for utility stack adoption.

## Revisit Trigger

Re-open this decision only when at least one is true:

- multi-theme requirements become mandatory
- component duplication across pages becomes high
- style refactor cost repeatedly blocks feature work
