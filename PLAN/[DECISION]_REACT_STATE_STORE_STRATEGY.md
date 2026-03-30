# [DECISION] React State Store Strategy (`2026-03-30`)

## Decision

For v1 online runtime, frontend state management is fixed to:

- stream lifecycle state: `useReducer` + typed reducer (`gameStreamReducer`)
- projection/derivation: selector modules
- transport side-effects: hook-local orchestration (`useGameStream`) + stream client class

`zustand` is not introduced in this phase.

## Why

1. Current feature scope is stream-centric and already normalized by `seq` reducer logic.
2. We already have deterministic reducer tests for ordering, rehydrate, and manifest hash handling.
3. Adding external store indirection now would increase migration surface without immediate reliability gain.
4. DI/adapter boundaries are preserved by contracts and selectors, so a store-library migration remains possible later.

## Guardrails

If v2 introduces multi-page concurrent UI state sharing or heavy local interaction state,
re-open this decision and evaluate:

- `zustand` adapter layer behind a `StorePort`
- migration only after parity checklist (`OI10`) passes
- preserve existing reducer tests as contract tests during migration

## Source Files (Current Baseline)

- `apps/web/src/hooks/useGameStream.ts`
- `apps/web/src/domain/store/gameStreamReducer.ts`
- `apps/web/src/domain/selectors/*`
