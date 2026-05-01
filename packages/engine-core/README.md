# packages/engine-core

Engine rule and state primitives extracted from legacy paths.

Current state:

- initial pure TypeScript rule primitives for movement, economy, and prompt choice legality
- legacy engine remains in the current legacy runtime tree
- property coverage lives in `apps/web/src/domain/rules/engineCore.rules.spec.ts`

The package intentionally keeps rules free of UI, Redis, and transport concerns.
Adapters can translate runtime state into these small inputs and apply the returned
mutation facts back to the host engine.
