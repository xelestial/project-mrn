# packages/engine-core

Engine rule and state primitives shared across runtime surfaces.

Current state:

- initial pure TypeScript rule primitives for movement, economy, and prompt choice legality
- current engine remains in the current runtime tree
- property coverage lives in `apps/web/src/domain/rules/engineCore.rules.spec.ts`

The package intentionally keeps rules free of UI, Redis, and transport concerns.
Host runtimes translate their state into these small inputs and apply the returned
mutation facts at module boundaries.
