# [PLAN] Parameter-Driven Runtime Decoupling

> Canonical location (migrated on 2026-03-31): `docs/architecture/parameter-driven-runtime-decoupling.md`  
> This `PLAN/` file remains as a compatibility mirror for existing links.

Status: `ACTIVE`  
Owner: `Shared (Execution: GPT for backend/frontend tracks)`  
Updated: `2026-03-31`  
Parents:
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`
- `PLAN/[PLAN]_ONLINE_GAME_INTERFACE_SPEC.md`
- `PLAN/[PLAN]_ONLINE_GAME_API_SPEC.md`
Related Review:
- `PLAN/[REVIEW]_PIPELINE_CONSISTENCY_AND_COUPLING_AUDIT.md`

## Purpose

Make backend/frontend resilient when game parameters change, by removing hardcoded assumptions and moving to a session-scoped parameter manifest + injected config pipeline.

This plan targets parameter volatility including (not limited to):

- tile layout/value changes
- character ability/priority changes
- initial resource changes (cash/shards/score)
- trick card content/usage constraints
- public message/label presentation
- dice card values/count and movement option generation

## Current Implementation Snapshot (`2026-03-31`)

Implemented baseline:

- backend resolver/manifest services are added:
  - `apps/server/src/services/parameter_service.py`
  - `apps/server/src/services/engine_config_factory.py`
- session create/get/start now include `parameter_manifest` in API payload.
- session start stream now emits `event_type=parameter_manifest`.
- resolver now supports session override `board_topology` (`ring`/`line`) for manifest-driven UI projection.
- runtime boot path now consumes resolved parameters via injected config factory.
- frontend baseline now consumes manifest for:
  - lobby join-seat options
  - board bootstrap fallback when snapshot is not yet available
- frontend stream reducer now resets/rehydrates message cache on manifest hash change.
- frontend app-side manifest merge path now rehydrates board topology + labels from stream manifest (tested helper path).
- stale-artifact gate helper baseline is added:
  - `tools/parameter_manifest_gate.py`
  - `tools/parameter_manifest_snapshot.json`
  - `apps/server/tests/test_parameter_manifest_snapshot.py` (snapshot sync gate)
- stream/session integration fixtures now include:
  - non-default seat+topology manifest scenario (`3-seat + line`)
  - reconnect replay validation for manifest variant payload visibility
- backend transport E2E fixture now validates reconnect replay after manifest-hash change
- web integration fixture now includes hash-change reconnect chain (`reducer -> selector -> manifest merge`)
- broader parameter-pack matrix coverage is now added and validated:
  - backend resolver/manifest variant tests for seat/economy/dice overrides
  - session API start-manifest variant verification
  - Playwright parity fixture for `2-seat + economy/dice overrides`
  - fixture integrity spec update for matrix fixture catalog
- root-source propagation verification is now added:
  - source file delta changes `source_fingerprints` + `manifest_hash`
  - session bootstrap manifest reflects source-change hash (`apps/server/tests/test_parameter_propagation.py`)
- external-AI participant/runtime defaults are now also parameter-driven enough for worker replacement:
  - `healthcheck_policy`
  - `require_ready`
  - `max_attempt_count`
  - `required_request_types`
  - `required_worker_adapter`
  - `required_policy_mode`
  - `required_policy_class`
  - `required_decision_style`
  - `worker_profile`
- `worker_profile=priority_scored` now expands stronger-worker compatibility requirements without repeating every low-level gate
- local session/API/runtime/playtest coverage now proves those worker-profile defaults survive through:
  - parameter resolution
  - session normalization
  - runtime compatibility checks
  - localhost HTTP worker round-trips

## Why This Is Needed (Current Audit)

Current runtime already has configurable pieces (`ruleset.json`, `GameConfig`, tile metadata), but several layers still bind to fixed assumptions.

### A) Backend/session/runtime hardcoded hotspots

1. Session seat count fixed to 4
- `apps/server/src/services/session_service.py`
  - `len(seats) != 4`, `seat > 4`
- `apps/server/src/routes/sessions.py`
  - `Field(..., ge=1, le=4)` for seat inputs

2. Runtime always boots `DEFAULT_CONFIG`
- `apps/server/src/services/runtime_service.py`
  - imports and passes `DEFAULT_CONFIG`
  - session `config` currently only used for seed

3. Prompt/stream timing constants are fixed values
- `apps/server/src/routes/stream.py`
  - heartbeat interval and wait timeout literals

### B) Engine hardcoded hotspots

1. Initial trick draw count fixed
- `GPT/engine.py`
  - `_draw_tricks(state, p, 5)`

2. Card/character/weather behavior keyed by display name strings
- `GPT/effect_handlers.py`
- `GPT/engine.py`
- `GPT/characters.py`
- `GPT/trick_cards.py`
- `GPT/weather_cards.py`

3. Dice option generation partly assumes 1..6
- `GPT/ai_policy.py`
  - multiple `range(1, 7)` branches
- `GPT/viewer/human_policy.py`
  - `range(1, 7)` for remaining dice cards

### C) Frontend hardcoded hotspots (React)

1. Board geometry fixed to 40-tile ring assumptions
- `apps/web/src/features/board/BoardPanel.tsx`
  - `ringPosition()` index buckets for 40 tiles
- `apps/web/src/styles.css`
  - fixed 11x11 board grid (`repeat(11, ...)`)

2. Lobby seat UX fixed to 4 seats
- `apps/web/src/App.tsx`
- `apps/web/src/features/lobby/LobbyView.tsx`
  - fixed Seat 1..4 options and default arrays

3. Message labels/helpers hardcoded in selector/component maps
- `apps/web/src/domain/selectors/streamSelectors.ts`
- `apps/web/src/features/prompt/PromptOverlay.tsx`

## Coupling/Hardcoding Review Findings (Document-Level)

This section records where plan/spec wording itself can re-introduce coupling.

## FND-1 (`High`) Fixed-size wording leaks into contracts

Examples:

- "4-seat mixed config" as default acceptance phrase
- "render 40-tile ring" as if mandatory contract

Risk:

- implementers may treat defaults as invariants
- API/frontend become implicitly locked to one profile

Plan:

- rewrite wording to "default profile" + "parameterized range"
- include explicit seat/topology capability fields in manifest

## FND-2 (`High`) Rule and display concerns are still co-located

Examples:

- label and helper text policy mixed with event semantics
- name-string routing and UX label changes can collide

Risk:

- content localization can accidentally affect gameplay routing
- replay parity breaks when display text changes only

Plan:

- split into:
  - immutable rule IDs (`character_id`, `card_id`, `event_code`)
  - mutable display catalogs (`labels`, `descriptions`, locale packs)

## FND-3 (`Medium`) Runtime config path is not fully explicit

Examples:

- docs mention session `config` but not strict precedence and merge policy

Risk:

- inconsistent behavior across runtime entrypoints
- hard-to-reproduce variant bugs

Plan:

- codify resolver precedence:
  1) engine defaults
  2) ruleset profile
  3) session overrides
  4) runtime-safe clamps/validation

## FND-4 (`Medium`) Frontend projection abstraction is underspecified

Examples:

- topology-driven rendering is named, but projection contract is still broad

Risk:

- reimplementation drift between React and future Unity client

Plan:

- define deterministic projection contract:
  - input: `topology + tile_count + anchor policy`
  - output: stable per-tile render coordinates and adjacency metadata
  - test fixtures shared across clients

## Target Architecture

## 1) Single runtime source: `ResolvedGameParameters`

Introduce a resolved parameter object generated per session:

- merged from:
  - baseline defaults
  - ruleset/variant overrides
  - explicit session config overrides
- validated once before runtime starts
- injected into engine adapter and exposed to frontend as public manifest

Proposed shape (high-level):

- `seat_limits`: min/max seat count
- `board`: tile topology, tile metadata, ring/path projection hints
- `economy`: initial cash, rent/purchase profiles
- `resources`: initial shards/score-hand values
- `dice`: dice card values, max cards per turn, composition policy
- `decks`: trick/fortune/weather metadata versions and counts
- `labels`: event labels / tile-kind labels / prompt helper packs
- `ui_hints`: optional presentation hints (non-rule)

## 1A) Root Source and Auto-Propagation Model

The system should treat config/data as a rooted graph, not scattered constants.

Canonical root sources:

- rules profile source (economy/resource/dice/end conditions)
- board topology source (tile metadata/layout)
- content source (characters/tricks/fortune/weather with stable IDs)
- label catalog source (event/tile/prompt display strings by locale/mode)

Derived artifacts (automatically built):

- engine-ready `ResolvedGameParameters`
- backend public `parameter_manifest`
- frontend typed `ParameterManifest` models
- compatibility index (`manifest_hash`, `manifest_version`, source fingerprints)

Propagation direction is strictly one-way:

`Root Source -> Resolver/Builder -> Engine Config + API Manifest -> Frontend Store/Selectors`

No reverse edits from frontend/backend to root source.

## 2) Public contract: `parameter_manifest`

Backend emits a stable public manifest for each session:

- included in:
  - `session_start`
  - first snapshot after reconnect
  - optional dedicated `parameter_manifest` event

Frontend must render from this manifest and not from fixed constants.

Required metadata:

- `manifest_version` (schema version)
- `manifest_hash` (content hash of resolved parameters)
- `source_fingerprints` (per-root-source checksums)

## 3) DI boundaries

Backend DI additions:

- `SessionConfigValidator`
- `GameParameterResolver`
- `EngineConfigFactory`
- `PublicManifestBuilder`

Frontend DI additions:

- `ParameterManifestStore`
- `LabelCatalogPort`
- `BoardProjectionPort`

## 4) Auto-Propagation Guarantees

When root source changes, reflected outputs must update without manual copy edits.

Guarantees:

1. Engine bootstrap uses resolver output only (never global literals).
2. Session/API bootstrap returns manifest generated from same resolver output.
3. Frontend hydration reads manifest first and computes view-model from it.
4. CI fails if source fingerprint changed but derived manifest/types are stale.

## Work Plan

## Phase P0 — Source Registry and Fingerprints

### Deliverables

1. Define root source registry (paths + schema IDs + owners).
2. Add fingerprint generation (`sha256`) for each root source.
3. Add combined `manifest_hash` generation rule.
4. Add CI check that fingerprints and manifest are synchronized.

### DoD

- Any root source modification changes fingerprint/hash deterministically.
- CI blocks merge if resolver output snapshot is stale.

## Phase P1 — Config Schema + Resolver (Backend)

### Deliverables

1. Add typed session config schema for gameplay parameters.
2. Validate incoming `config` in session creation.
3. Build `ResolvedGameParameters` from defaults + overrides.
4. Store resolved parameters in session state (not raw dict-only).
5. Add resolver precedence table and clamp policy to docs and tests.
6. Emit `manifest_hash` and `source_fingerprints` from resolver output.

### DoD

- Invalid parameter values fail fast with explicit error codes.
- Runtime start does not read global defaults directly.

## Phase P2 — Engine Adapter Decoupling

### Deliverables

1. Replace direct `DEFAULT_CONFIG` runtime boot with `EngineConfigFactory`.
2. Move fixed draw/initialization literals to config fields:
   - initial trick draw count
   - timing defaults used by runtime adapter
3. Reduce name-string branching by introducing stable IDs where possible:
   - card IDs and character IDs become dispatch keys
   - display names remain presentation-only
4. Add compatibility adapter for legacy text-keyed logs/replays.

### DoD

- Changing initial resource/dice/tile config does not require code edits in runtime service.
- Engine startup path is pure DI (`resolver -> config factory -> engine`).

## Phase P3 — Stream/API Contract Expansion

### Deliverables

1. Extend API spec with session parameter manifest payload.
2. Extend WS event contract with parameter manifest event/version.
3. Add manifest version/hash field for replay compatibility.
4. Add "default profile vs parameterized fields" table in API spec examples.
5. Add reconnect rule: if `manifest_hash` changed, client must rehydrate projection state.

### DoD

- Reconnected client can fully rebuild UI assumptions from stream/API alone.
- Contract tests cover missing/partial manifest handling.

## Phase P4 — Frontend Dynamic Rendering

### Deliverables

1. Replace fixed ring mapping with topology-driven projection from manifest.
2. Replace fixed seat count UI with manifest-provided seat range/list.
3. Move labels/helpers from hardcoded maps to label catalog delivered from backend (with local fallback).
4. Keep selectors resilient to unknown tile kinds/event kinds.
5. Enforce rule-id vs display-label split in selector/view-model layer.
6. Add manifest-hash guard in client store:
   - mismatch triggers full projection reset and rehydrate.

### DoD

- Tile count/layout changes render without frontend code edits.
- Seat count/policy changes reflect in lobby/match UI automatically.

## Phase P5 — Rule/Content Volatility Hardening

### Deliverables

1. Add stable IDs in card/character datasets where missing.
2. Keep effect routing keyed by IDs.
3. Add compatibility layer for legacy name-based saves/replays.
4. Add snapshot/replay tests with alternative parameter packs.
5. Add doc lint checks for fixed-size language (`4-seat`, `40-tile`) in contract/spec docs.

### DoD

- Content text changes (names/descriptions) do not break engine behavior routing.
- Replay remains readable with old and new label packs.

## Example Impact Matrix

| Change example | Current impact | After this plan |
|---|---|---|
| Tile count/layout changed | board projection/UI break | manifest-driven topology renders dynamically |
| Tile value/rent profile changed | partial config + selector assumptions | full runtime + UI from resolved manifest |
| Character ability text changed | risk in name-string dispatch | ID-based effect routing + separate label pack |
| Initial cash/shards changed | engine supports, runtime bridge partially fixed | session-config to runtime end-to-end |
| Trick usage constraints changed | mixed (hardcoded checks) | ruleset + resolver + prompt generation from config |
| Dice value set changed | `range(1,7)` hotspots | dice values from config in policy/human prompt/UI |
| Message/label format changed | frontend maps must be edited | label catalog + fallback strategy |

## Test Strategy

## Backend tests

- Config schema validation tests:
  - bounds, types, unknown keys policy
- Runtime boot tests:
  - custom config applies to engine state
- Contract tests:
  - parameter manifest appears in required events
- Fingerprint tests:
  - source edit changes `source_fingerprints` and `manifest_hash`

## Frontend tests

- Board projection tests with non-40 tile fixtures
- Seat/lobby tests with variable seat fixtures
- Label fallback tests for unknown event/tile kinds
- Hydration tests:
  - manifest hash change forces projection refresh

## E2E tests

- Scenario A: baseline pack (current rules)
- Scenario B: modified economy + dice values
- Scenario C: altered tile topology
- Scenario D: label-only catalog update (no rule behavior regression)
- Scenario E: root source update propagates in a single run (engine/api/frontend parity)

## Documentation and Governance Rules

For any gameplay-parameter change:

1. update parameter schema docs
2. update resolver/manifest tests
3. update API/interface specs if payload changed
4. update plan status in:
   - `PLAN/PLAN_STATUS_INDEX.md`
   - `PLAN/[PLAN]_REACT_ONLINE_GAME_DETAILED_EXECUTION.md`

## Guardrails (Must Hold)

1. Defaults are examples, not invariants.
2. Rule evaluation must use stable IDs, not localized display strings.
3. Frontend layout logic must read topology manifest first, then fallback.
4. Any fixed-size literal in API/interface/component specs requires explicit `default-profile` annotation.
5. Root source changes must flow through resolver/builder only; no manual cross-layer patching.

## Exit Criteria for This Plan

- Session runtime boots from resolved parameters in all online entrypoints.
- React board/lobby render correctly with non-default seat/topology fixtures.
- API/interface specs expose manifest fields as first-class contract.
- Contract tests confirm behavior parity across at least:
  - default profile
  - modified seat profile
  - modified tile topology profile
- Source update auto-propagation is proven by CI scenario:
  - one root-source edit
  - regenerated resolver output
  - backend session bootstrap reflects new hash
  - frontend rehydrates and renders updated state without code edits

## Progress Update (`2026-03-31`)

Current closure level for priority phases:

- `P0` Source registry/fingerprint baseline: `DONE (baseline)`
  - root-source fingerprint builder + manifest hash are wired
  - snapshot stale gate is active in CI (`tools/parameter_manifest_gate.py --check`)
  - rerun verification (`2026-03-31`) passed:
    - `python tools/parameter_manifest_gate.py --check`
    - `python tools/encoding_gate.py`
    - `python tools/legacy_path_audit.py --roots apps packages tools --strict`
    - backend parameter suite: `11 passed, 8 skipped`
    - web manifest/selector suite: `15 passed`
- `P1` Config schema/resolver baseline: `DONE (baseline)`
  - session config validation + resolved parameter path are live
  - invalid ranges/types fail fast with stable error reasons
- `P2` Engine adapter decoupling baseline: `DONE (baseline)`
  - runtime boot path now routes through `EngineConfigFactory`
  - direct runtime default boot dependency removed from service entrypoint
- `P3` Stream/API expansion baseline: `DONE (baseline)`
  - session API + stream include `parameter_manifest` and hash metadata
  - reconnect replay fixtures + reducer rehydrate guard are covered
  - browser playbook fixtures are versioned and integrity-tested
  - Playwright browser e2e baseline is now active in CI (`apps/web/e2e/parity.spec.ts`)
- broader parameter-pack matrix closure: `DONE`
  - backend tests now cover seat/economy/dice matrix resolve + manifest hash deltas
  - API start payload now validated against matrix manifest profile
  - Playwright parity suite now includes matrix fixture (`parameter_matrix_economy_dice_2seat`)

Remaining for full closure:
- none for current decoupling baseline scope; next work belongs to content-ID hardening (`P5`)

## Out of Scope (for this plan)

- Full game-balance redesign
- AI strategy tuning unrelated to parameterization seam
- Production persistence/database migration
