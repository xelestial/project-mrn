# [PLAN] Repository Directory Specification

Status: `ACTIVE`  
Owner: `Shared`  
Updated: `2026-03-29`  
Parents:
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`

## Purpose

Define where code and documents should live as the project transitions from `GPT/`-heavy layout to a scalable online-game architecture.

This specification answers:

- which directory each concern belongs to
- where new code should be written first
- how to migrate from legacy `GPT/` and `CLAUDE/` paths safely

## Decision Summary

Yes, separating new online-runtime code out of `GPT/` is the right direction.

Rationale:

- lower coupling between engine/policy/view/runtime
- easier DI and testing boundaries
- better long-term portability (Unity client, additional web clients)
- clearer ownership for GPT vs CLAUDE workstreams

## Target Top-Level Layout

```text
apps/
  server/                     # FastAPI online runtime (session, ws, prompt routing)
  web/                        # React playable viewer/client

packages/
  engine-core/                # shared game domain/rules interfaces + core primitives
  runtime-contracts/          # shared event/prompt/public-state schemas
  replay-core/                # replay projection, timeline parsing, summary helpers
  policy-gpt/                 # GPT-side policy modules
  policy-claude/              # CLAUDE-side policy modules
  ui-domain/                  # front-end domain mappers/selectors not tied to React

tools/
  scripts/                    # operational scripts (run, export, validation wrappers)
  checks/                     # lint/check/test orchestration scripts

tests/
  contract/                   # backend/frontend contract conformance
  integration/                # ws/session/prompt integration
  e2e/                        # browser-level tests

docs/
  architecture/               # architecture specs and ADRs
  api/                        # REST/WS specs
  frontend/                   # component specs and UX contracts
  backend/                    # backend services/DI/runtime docs

plan/                         # active planning docs (current: PLAN/)
data/                         # game data tables/spec snapshots (current: DATA/)
result/                       # generated outputs/artifacts
balance/                      # rule/balance change records
pattern/                      # strategy pattern notes
sync/                         # cross-agent handoff artifacts

legacy/
  gpt/                        # transitional mirror of current GPT/
  claude/                     # transitional mirror of current CLAUDE/
```

## Naming Policy

Directory naming policy:

- new top-level runtime modules should use lowercase (`apps`, `packages`, `docs`, `plan`, `data`).
- current uppercase directories (`PLAN`, `DATA`, `SYNC`) remain valid during migration.
- no forced rename in one step; use staged migration with redirects.

File naming policy:

- plans: `[PLAN]_...`
- proposals: `[PROPOSAL]_...`
- agreements: `[AGREE]_...`
- architecture decisions: `[ADR]_...`

## Write-Location Rules (Effective Immediately)

For new online game implementation work:

1. Server/API/WebSocket code:
   - write in `apps/server/` (not `GPT/`).
2. React client code:
   - write in `apps/web/` (not `GPT/viewer/`).
3. Contract schemas/parsers:
   - write in `packages/runtime-contracts/`.
4. Replay/public projection logic:
   - write in `packages/replay-core/`.
5. Engine policy code:
   - new GPT policy modules in `packages/policy-gpt/`
   - new CLAUDE policy modules in `packages/policy-claude/`.

Temporary exception:

- if migration seam is not ready, a compatibility adapter may remain in legacy paths, but new behavior must be implemented in target paths first.

## Legacy-to-Target Mapping

| Current Path | Target Path | Migration Rule |
|---|---|---|
| `GPT/viewer/` | `apps/web/src/` + `packages/replay-core/` | split UI rendering vs projection |
| `GPT/viewer/renderers/` | `apps/web/src/features/*` | renderer logic moved to React feature components |
| `GPT/viewer/replay.py` | `packages/replay-core/` | pure projection/parser extraction first |
| `GPT/engine.py` | `packages/engine-core/` | keep wrapper in legacy until consumers moved |
| `GPT/effect_handlers.py` | `packages/engine-core/` | move with rule parity tests |
| `CLAUDE/server/*` (planned) | `apps/server/` | use as canonical runtime service host |
| `PLAN/*` | `plan/*` (future) | migrate after toolchain path compatibility check |
| `DATA/*` | `data/*` (future) | keep duplicated pointer docs during transition |

## Backend Directory Detail (`apps/server`)

```text
apps/server/
  src/
    app.py                    # composition root
    routes/
      sessions.py
      stream.py
      health.py
    services/
      session_service.py
      runtime_service.py
      prompt_service.py
      auth_service.py
    domain/
      session_models.py
      runtime_models.py
    infra/
      ws/
      logging/
      storage/
    adapters/
      engine_adapter.py
      policy_router.py
  tests/
    unit/
    integration/
```

## Frontend Directory Detail (`apps/web`)

```text
apps/web/
  src/
    app/
    core/                     # DI, config, logger, shared app services
    domain/                   # state slices, reducers, selectors, view models
    infra/                    # REST/WS clients
    features/
      lobby/
      board/
      players/
      prompt/
      theater/
      timeline/
      status/
      replay/
    shared/
      ui/
      styles/
      utils/
  tests/
    unit/
    integration/
    e2e/
```

## Shared Packages Detail

## `packages/runtime-contracts`

- event envelope schemas
- prompt/decision schemas
- codec/parser validators
- compatibility aliases and migration notes

## `packages/replay-core`

- event timeline parser
- projection reducers
- replay cursor/controller primitives

## `packages/engine-core`

- rule/effect primitives
- immutable state structures
- engine-side domain interfaces

## Migration Phases

## Phase D1: Scaffolding

- create `apps/`, `packages/`, `docs/`, `tests/` roots
- add README pointers from legacy folders

## Phase D2: Contract and Replay Extraction

- move contracts to `packages/runtime-contracts`
- move replay projection to `packages/replay-core`
- keep backward import adapters in legacy folders

## Phase D3: Web and Server Runtime Move

- move new React implementation to `apps/web`
- move session/ws runtime to `apps/server`
- wire adapters for legacy scripts temporarily

## Phase D4: Engine/Policy Segmentation

- extract shared engine pieces to `packages/engine-core`
- split policy code into `packages/policy-gpt` / `packages/policy-claude`

## Phase D5: Legacy Freeze

- legacy directories become read-only except adapters
- all new features required to land in target directories

## Quality and Safety Rules

- No destructive mass move without parity tests.
- Every moved module must keep behavior parity with snapshots/tests.
- Import path changes must be covered by at least:
  - one unit test
  - one integration test on moved seam.
- Compatibility adapters are temporary and must include removal TODO with owner.

## Ownership Split

- GPT:
  - `apps/web`
  - `packages/replay-core`
  - `packages/policy-gpt`
- CLAUDE:
  - `apps/server`
  - `packages/policy-claude`
  - backend runtime ops/logging seams
- Shared:
  - `packages/runtime-contracts`
  - `packages/engine-core`
  - `docs/api`, `docs/architecture`, `plan`

## Immediate Next Actions

1. Approve this directory specification as active.
2. Create empty scaffold directories with README placeholders.
3. Start React and server work in `apps/*` only.
4. Track legacy-path usage in migration checklist until zero.
