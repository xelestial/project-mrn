# [PROMPT] Project MRN 3D From Scratch

Status: REFERENCE_PROMPT  
Owner: Frontend / Product / Runtime  
Updated: 2026-05-11

## Purpose

This document contains a single integrated prompt for creating a new Project-MRN-like 3D web board game from scratch.

Use this prompt when starting a new repository or asking an implementation agent to scaffold a fresh game project. Do not use it as an instruction to modify the existing Project-MRN repository directly.

For work inside the existing Project-MRN repository, use the active runtime/frontend/backend docs instead.

---

## Integrated Prompt

```text
You are a senior full-stack game engineer, technical architect, and gameplay systems designer.

Create a new project from scratch: a 3D web board game inspired by Project-MRN.

The game is a Korean/Joseon-fantasy turn-based strategic board game that combines:
- Monopoly / Blue Marble-style tile ownership and rent economy
- role drafting
- hidden / visible card play
- weather events
- fortune events
- dice and dice-card movement
- character abilities
- psychological target guessing
- human and AI players
- online session play
- a 3D board rendered in the browser

The goal is to build a playable MVP, not a visual mockup.

Prioritize:
1. deterministic game rules
2. backend-authoritative state
3. stable prompt/decision flow
4. playable 3D board UI
5. tests
6. clear documentation

Do not build a purely frontend-only toy.
The game engine must be deterministic and testable.
The backend must own gameplay truth.
The 3D frontend must only render state and submit legal decisions.

# 1. Product Summary

Build a 1–4 player online 3D web board game.

Working title:
- Project MRN 3D

Genre:
- turn-based strategy board game
- Korean/Joseon-fantasy board game
- property ownership / rent economy
- role-drafting tactical game
- card-effect-driven party strategy game

Player count:
- 1 to 4 players

Seat types:
- human
- AI

AI profiles:
- random
- balanced
- aggressive
- defensive

Theme:
- Korean/Joseon-fantasy
- currency: 냥
- special resource: 미리내 조각
- score object: 승점 토큰 / score coin
- characters inspired by historical/fantasy roles such as 어사, 탐관오리, 자객, 산적, 추노꾼, 탈출 노비, 파발꾼, 아전, 교리 연구관, 교리 감독관, 박수, 만신, 객주, 중매꾼, 건설업자, 사기꾼

Important design principle:
- Korean names are presentation labels only.
- Gameplay logic must use stable internal IDs.
- Never evaluate rules by Korean display text.

# 2. Required Tech Stack

Create a monorepo.

Recommended stack:

Backend:
- Python 3.11+
- FastAPI
- WebSocket
- Pydantic
- Redis for authoritative runtime/session/prompt state
- pytest

Frontend:
- React
- TypeScript
- Vite
- Three.js
- @react-three/fiber
- @react-three/drei
- Zustand or Redux Toolkit for frontend state
- Vitest
- Playwright for browser smoke tests

Contracts:
- shared JSON schemas or TypeScript/Python matching models
- runtime contract examples for WebSocket messages

DevOps:
- Docker Compose for Redis + backend + frontend
- README with local run instructions

# 3. Required Project Structure

Create this structure:

project-mrn-3d/
  README.md
  docker-compose.yml
  docs/
    Game-Rules.md
    Architecture.md
    API.md
    Runtime-Contract.md
    3D-Board-Rendering-Contract.md
    3D-Interaction-And-Prompt-Mapping.md
    3D-Visibility-And-Animation-Rules.md
  engine/
    __init__.py
    models.py
    engine.py
    board.py
    cards.py
    characters.py
    effects.py
    prompts.py
    ai_policy.py
    scoring.py
    tests/
  apps/
    server/
      pyproject.toml
      src/
        app.py
        routes/
          sessions.py
          websocket.py
        services/
          session_service.py
          runtime_service.py
          prompt_service.py
          stream_service.py
          redis_store.py
        domain/
          view_state.py
          auth.py
          errors.py
        contracts/
          api_models.py
          ws_models.py
      tests/
    web/
      package.json
      vite.config.ts
      index.html
      src/
        main.tsx
        App.tsx
        api/
          sessionApi.ts
          streamClient.ts
        domain/
          store.ts
          selectors.ts
          types.ts
          promptMapping.ts
        features/
          lobby/
          hud/
          prompt/
          scene3d/
            GameCanvas3D.tsx
            BoardScene.tsx
            BoardCamera.tsx
            BoardLights.tsx
            BoardTile3D.tsx
            PlayerPawn3D.tsx
            PropertyMarker3D.tsx
            ScoreCoin3D.tsx
            MovementPath3D.tsx
            TileSelectionLayer3D.tsx
            SceneHudBridge.tsx
            boardLayout3d.ts
            sceneTypes.ts
            promptTargetMapping3d.ts
        styles.css
        tests/
      e2e/
  packages/
    runtime-contracts/
      ws/
        schemas/
        examples/
    ui-domain/
      gameplay_catalog.json

# 4. Game Rules

## 4.1 Initial Setup

Each player starts with:
- 20 냥
- 2 미리내 조각
- 0 score coins
- 5 trick cards
- dice cards: 1, 2, 3, 4, 5, 6

Default game config:
- player count: 1–4
- default board topology: 40-tile square ring
- default end timer: 15
- default dice count: 2
- default seed: configurable
- deterministic random source required

## 4.2 Board

Create a 40-tile square ring board.

Tile types:
- START
- END_TIME_1
- END_TIME_2
- PROPERTY
- FORTUNE

Board layout:
- tile 0 = START
- tile 0 is front-left corner in 3D view
- tile 10 = front-right corner
- tile 20 = back-right corner
- tile 30 = back-left corner
- movement proceeds clockwise
- tile 39 is immediately before returning to tile 0

Property tile fields:
- tile_id
- tile_index
- display_name
- tile_color
- district_id
- purchase_cost
- base_rent
- owner_player_id
- score_coin_count
- is_hostile

Districts:
- property tiles belong to districts of 2 or 3 tiles
- if one player owns every tile in a district, it becomes a monopoly
- monopoly tiles cannot be forcibly acquired in MVP

Property rules:
- landing on unowned property: player may buy it
- landing on own property: player may place score coin if allowed
- landing on another player’s property: player pays rent
- inability to pay required rent causes bankruptcy
- inability to buy property does not cause bankruptcy

Hostile region:
- when a player goes bankrupt, their properties become hostile
- hostile rent is paid to the bank
- hostile rent is 3x base rent or another documented value

## 4.3 Round Flow

Each round:

1. Reveal one weather card.
2. Draft character cards.
3. Each player chooses one final character.
4. Determine turn order by character priority.
5. Each player takes one turn.
6. Resolve round-end effects.
7. Flip active character faces when doctrine characters require it.
8. Start next round unless end condition is met.

## 4.4 Turn Flow

Each player turn:

0. Resolve mark/target effects against this player.
1. Resolve character start ability.
2. Allow trick card use.
3. Roll dice or use dice cards.
4. Move pawn.
5. Resolve arrival:
   - START / lap reward
   - END_TIME tile
   - FORTUNE tile
   - own property
   - unowned property purchase
   - other player property rent
   - score coin placement
   - character/trick/weather follow-up effects
6. Save turn-end snapshot.

## 4.5 Character Cards

Create 8 character slots. Each slot has two faces. Only one face per slot is active at a time.

Character slots:

1. official / corrupt_official
   - 어사
   - 탐관오리

2. assassin / bandit
   - 자객
   - 산적

3. bounty_hunter / escaped_slave
   - 추노꾼
   - 탈출 노비

4. courier / clerk
   - 파발꾼
   - 아전

5. doctrinal_researcher / doctrinal_supervisor
   - 교리 연구관
   - 교리 감독관

6. shaman / manshin
   - 박수
   - 만신

7. merchant / matchmaker
   - 객주
   - 중매꾼

8. builder / fraudster
   - 건설업자
   - 사기꾼

Each character must have:
- character_id
- display_name
- slot
- face_id
- priority
- traits
- ability_id
- ability handler

MVP must implement at least these abilities:

- assassin:
  - chooses a hidden character target
  - if correct, disables that character’s turn this round

- bandit:
  - marks a hidden character target
  - if target is later revealed, steals money from that player

- bounty_hunter:
  - marks a hidden character target
  - when target player’s turn starts, move that player to bounty hunter’s last tile

- courier:
  - modifies dice mode this turn

- clerk:
  - collects tax from players on same tile after arrival

- merchant:
  - gets bonus resource from lap / end / own-tile reward

- builder:
  - discounts or waives property purchase cost

- fraudster:
  - may acquire a non-monopoly property under special acquisition cost

Implement the remaining characters with simple placeholder abilities but preserve stable interfaces.

## 4.6 Character Draft

For 4 players:
- shuffle active character faces
- draw 4
- first draft proceeds from marker owner in marker direction
- draw 4 again
- second draft proceeds in reverse order
- each player has 2 candidate characters
- each player chooses one final character
- if only one option exists, auto-select

For 1–3 players:
- implement simplified draft that gives each player at least 2 candidate choices when possible

Marker:
- marker owner determines first draft picker
- marker direction is clockwise or counterclockwise
- doctrine characters can change marker owner and direction

## 4.7 Weather Cards

At round start, reveal one weather card.

Weather card fields:
- weather_id
- display_name
- effect_id
- description
- handler

MVP weather effects:
- all players pay 2 냥
- extra die this round
- no lap reward this round
- one property color rent x2
- draw one trick card
- end timer decreases by 1 or 3
- shard reward increases by 1

## 4.8 Fortune Cards

When landing on FORTUNE:
- reveal one fortune card
- apply immediately

MVP fortune effects:
- gain money
- lose money
- gain shard
- move backward
- move to nearest property
- move to nearest fortune tile
- reroll movement
- steal small amount from richest player

## 4.9 Trick Cards

Each player starts with 5 trick cards.

Rules:
- player may use at most one trick card per turn
- trick timing is after character ability and before dice roll
- one trick card may be hidden; others are visible
- hidden/private state must be viewer-specific

MVP trick effects:
- avoid rent once
- move to nearest fortune tile
- move to farthest player
- add movement
- subtract movement
- draw trick card
- exchange burden card
- force another player to pay small tax

Burden cards:
- negative cards
- may cost money to remove during resupply or burden exchange
- do not need full complexity in MVP, but model the concept

## 4.10 Dice Cards

Each player starts with dice cards 1–6.

Default movement:
- roll 2 dice

Dice card use:
- player may replace one die with one dice card
- optional: allow replacing both dice with two dice cards
- used dice cards are removed
- dice card availability is private to that player unless explicitly revealed

## 4.11 Lap Reward

When a player passes or lands on START:
- grant lap reward

MVP lap reward:
- player chooses from:
  - money
  - shard
  - score coin
- use a point budget system if practical
- otherwise implement simple choice:
  - +4 냥
  - +1 shard
  - +1 score coin

Merchant bonus:
- merchant gets +1 extra unit of selected reward or a clearly documented bonus

## 4.12 Score Coins

Score coins are victory tokens placed on owned property.

Rules:
- when landing on own property, player may place one score coin
- max visible score coins per tile: 3
- score coins contribute to final score
- first purchase turn may restrict placement if implemented

## 4.13 Bankruptcy

Bankruptcy occurs when a player cannot pay required money.

Required money includes:
- rent
- weather tax
- fortune loss
- character effect payment
- burden removal cost when mandatory

Bankruptcy result:
- player is marked bankrupt
- player-owned properties become hostile
- hostile properties charge bank rent
- bankrupt player may be eliminated or continue as inactive; choose and document one MVP behavior

Recommended MVP:
- bankrupt player is eliminated from future turns
- their pawns remain visually marked as bankrupt
- their properties become hostile regions

## 4.14 Game End Conditions

End the game when any condition is met:
- end timer reaches 0
- one player owns at least 9 properties
- one player owns at least 3 monopolies
- alive players are at most 1 or 2 depending on config

MVP scoring:
- score coins: 5 points each
- money: 1 point per 2 냥
- shards: 2 points each
- owned properties: 2 points each
- monopolies: 5 points each
- bankrupt players rank below non-bankrupt players

Show final ranking with score breakdown.

# 5. Backend Architecture

Backend must expose REST + WebSocket.

## REST API

Implement:

- POST /api/v1/sessions
  - create session
  - specify seats, AI profiles, config, seed

- GET /api/v1/sessions
  - list sessions

- GET /api/v1/sessions/{session_id}
  - get session state summary

- POST /api/v1/sessions/{session_id}/join
  - join as human seat

- POST /api/v1/sessions/{session_id}/start
  - start session

- GET /api/v1/sessions/{session_id}/view-commit
  - get latest authoritative view state for viewer

- GET /api/v1/sessions/{session_id}/replay
  - debug replay export

- GET /api/v1/sessions/{session_id}/runtime-status
  - runtime status

## WebSocket API

Implement:

- WS /api/v1/sessions/{session_id}/stream?token=...

Server-to-client message types:
- view_commit
- event
- prompt
- decision_ack
- error
- heartbeat

Client-to-server message types:
- decision
- resume

## API Envelope

All REST responses:

{
  "ok": true,
  "data": {},
  "error": null
}

Errors:

{
  "ok": false,
  "data": null,
  "error": {
    "code": "INVALID_STATE_TRANSITION",
    "category": "state",
    "message": "Session cannot be started from current state.",
    "retryable": false
  }
}

## Prompt / Decision Contract

Prompt fields:
- request_id
- request_type
- player_id
- timeout_ms
- choices
- public_context
- effect_context if caused by character/trick/weather/fortune

Decision fields:
- request_id
- player_id
- choice_id
- choice_payload
- view_commit_seq_seen
- prompt_instance_id or resume_token if implemented

Decision rules:
- first valid decision wins
- duplicate decisions return stale
- stale request_id returns stale
- wrong player returns error
- timeout triggers deterministic fallback
- AI decisions go through same validation path where possible

Prompt request types:
- draft_card
- final_character
- trick_to_use
- hidden_trick_card
- movement
- purchase_tile
- mark_target
- coin_placement
- lap_reward
- burden_exchange
- active_flip
- trick_tile_target
- specific_trick_reward
- runaway_step_choice

# 6. Runtime / Engine Requirements

The engine must be deterministic.

Required:
- seedable RNG
- serializable game state
- pure-ish rule functions where practical
- replay event log
- unit tests for core rules

The engine must not depend on FastAPI or React.

Runtime loop:
- backend starts engine for a session
- engine advances until it needs input
- backend stores pending prompt
- frontend/AI submits decision
- backend validates decision
- engine resumes
- backend publishes new view_commit

Redis:
- store session state
- store latest view_commit per viewer or per session
- store active prompt
- store event log
- store runtime status

MVP may use in-memory fallback for development, but Redis path must exist.

# 7. View State Contract

Create backend-owned `ViewCommit`.

Fields:

```ts
type ViewCommit = {
  schema_version: number;
  commit_seq: number;
  session_id: string;
  viewer: {
    role: "seat" | "spectator" | "host";
    player_id?: number;
    seat?: number;
  };
  runtime: {
    status: "waiting" | "in_progress" | "waiting_input" | "completed" | "failed";
    round_index: number;
    turn_index: number;
    active_player_id?: number;
  };
  view_state: ViewState;
};
```

ViewState includes:
- board
- players
- weather
- active character slots
- player cards visible to viewer
- prompt active for viewer
- hand tray visible to viewer
- event feed
- scene information for 3D board

Board view:

```ts
type BoardView = {
  topology: "ring";
  tile_count: 40;
  tiles: TileView[];
  last_move?: {
    player_id: number;
    from_tile_index: number;
    to_tile_index: number;
    path_tile_indices: number[];
  };
};
```

Tile view:

```ts
type TileView = {
  tile_index: number;
  tile_id: string;
  tile_kind: "start" | "end_time" | "property" | "fortune";
  tile_label: string;
  tile_color?: string;
  owner_player_id?: number | null;
  pawn_player_ids: number[];
  score_coin_count: number;
  purchase_cost?: number;
  rent?: number;
  is_hostile?: boolean;
};
```

# 8. 3D Frontend Requirements

The 3D frontend is the primary board presentation.

Use:
- React Three Fiber
- Three.js
- Drei

## 8.1 3D Board Defaults

Use these initial constants:

```ts
export const BOARD_3D_DEFAULTS = {
  topology: "ring",
  tileCount: 40,
  sideTileCount: 10,
  tile: {
    width: 1.0,
    depth: 1.0,
    height: 0.16,
    gap: 0.08,
    bevelRadius: 0.04,
  },
  table: {
    padding: 1.0,
    height: 0.18,
    y: -0.16,
  },
  pawn: {
    radius: 0.13,
    height: 0.42,
    baseHeight: 0.06,
    yOffset: 0.28,
  },
  scoreCoin: {
    radius: 0.12,
    height: 0.04,
    yOffset: 0.22,
    maxVisiblePerTile: 3,
  },
  propertyMarker: {
    width: 0.72,
    height: 0.08,
    depth: 0.08,
    yOffset: 0.14,
  },
} as const;
```

Coordinate system:
- X/Z board plane
- Y up
- board center at `[0, 0, 0]`

Camera:

```ts
export const DEFAULT_BOARD_CAMERA = {
  type: "orthographic",
  position: [7.5, 9.0, 7.5],
  target: [0, 0, 0],
  zoom: 62,
  near: 0.1,
  far: 100,
  minZoom: 42,
  maxZoom: 110,
  enableRotate: true,
  enablePan: true,
  enableZoom: true,
  minPolarAngle: Math.PI / 5,
  maxPolarAngle: Math.PI / 2.7,
  resetTransitionMs: 350,
} as const;
```

Player colors:

```ts
export const PLAYER_COLOR_DEFAULTS = {
  1: "#ef476f",
  2: "#118ab2",
  3: "#06d6a0",
  4: "#ffd166",
} as const;
```

Tile colors:

```ts
export const TILE_KIND_COLOR_DEFAULTS = {
  start: "#f8fafc",
  end_time: "#f97316",
  fortune: "#8b5cf6",
  property_black: "#111827",
  property_red: "#dc2626",
  property_yellow: "#eab308",
  property_blue: "#2563eb",
  property_white: "#e5e7eb",
  property_green: "#16a34a",
  hostile: "#7f1d1d",
  unknown: "#64748b",
} as const;
```

## 8.2 3D Components

Implement:

features/scene3d/
  GameCanvas3D.tsx
  BoardScene.tsx
  BoardCamera.tsx
  BoardLights.tsx
  BoardTile3D.tsx
  PlayerPawn3D.tsx
  PropertyMarker3D.tsx
  ScoreCoin3D.tsx
  MovementPath3D.tsx
  TileSelectionLayer3D.tsx
  SceneHudBridge.tsx
  boardLayout3d.ts
  promptTargetMapping3d.ts
  sceneTypes.ts

## 8.3 Tile Projection

Implement:

```ts
function projectTileTo3DPosition(
  tileIndex: number,
  tileCount = 40
): Tile3DTransform
```

Rules:
- tileCount other than 40 fails loudly in MVP
- tile 0 = front-left corner
- tile 10 = front-right corner
- tile 20 = back-right corner
- tile 30 = back-left corner
- clockwise ring

## 8.4 Pawn Placement

One tile may hold up to 4 pawns.

Pawn slot offsets:

```ts
export const PAWN_SLOT_OFFSETS = [
  [-0.24, 0.00,  0.24],
  [ 0.24, 0.00,  0.24],
  [-0.24, 0.00, -0.24],
  [ 0.24, 0.00, -0.24],
] as const;
```

Slot order:
- ascending player_id

## 8.5 Score Coin Placement

Score coin slot offsets:

```ts
export const SCORE_COIN_SLOT_OFFSETS = [
  [ 0.00, 0.00, -0.36],
  [-0.18, 0.00, -0.36],
  [ 0.18, 0.00, -0.36],
] as const;
```

Render:
- max 3 visible coins
- exact count in tooltip / HUD

## 8.6 3D Interaction

Interaction mode:
- focus-then-confirm
- no single-click submit in MVP

Click behavior:
- click tile with no matching prompt: inspect tile
- click tile with matching prompt target: focus target
- final submit happens through confirm button or existing prompt action
- invalid click never submits command

Prompt-to-3D target support:
- purchase_tile -> tile
- coin_placement -> tile
- trick_tile_target -> tile
- runaway_step_choice -> tile when stable target exists

Keep these 2D-only in MVP:
- draft_card
- final_character
- trick_to_use
- hidden_trick_card
- movement
- lap_reward
- burden_exchange
- active_flip

## 8.7 Animation

Animation is cosmetic only.

Defaults:

```ts
export const BOARD_ANIMATION_DEFAULTS = {
  pawnStepMs: 180,
  pawnStepMaxMs: 260,
  pawnHopHeight: 0.18,
  pawnSettleMs: 120,
  purchaseFlashMs: 450,
  rentTransferMs: 550,
  scoreCoinPlaceMs: 360,
  weatherRevealMs: 700,
  fortuneRevealMs: 650,
  hostileRegionConvertMs: 650,
  focusTileMs: 220,
  cameraFocusMs: 350,
  maxQueuedVisualEvents: 6,
} as const;
```

Rules:
- prompts appear immediately even during animation
- new ViewCommit cancels stale animation
- reconnect renders static authoritative state first
- no replay of old movement on reconnect
- latest ViewCommit always wins

## 8.8 3D Asset Policy

MVP:
- primitive meshes only
- no GLB dependency
- no character-specific models
- no physics
- no postprocessing
- no WebXR

Allowed:
- box tiles
- cylinder/rounded pawn
- coin cylinders
- ownership rails
- simple board table
- simple highlight/pulse effects

# 9. Frontend UI Requirements

Screens:
1. Lobby
2. Create session
3. Join session
4. Main game screen
5. Game over screen

Main game screen:
- 3D board canvas
- 2D player panels
- 2D prompt overlay
- 2D hand/trick tray
- 2D event feed
- current weather display
- round/turn display
- runtime/connection status
- camera reset button
- tile inspection tooltip/panel

Important:
- 3D board is visual hero
- 2D HUD remains responsible for dense text
- 2D prompt overlay remains fully usable
- game must be playable without perfect 3D art

# 10. Visibility Rules

Protect private information.

Do not reveal:
- other players’ hidden trick cards
- unrevealed final character choices
- private draft candidates
- private dice cards
- private burden choices

Spectator:
- sees only public/revealed state

Seat viewer:
- sees own private state
- sees other players’ public state only

Debug mode:
- may show IDs
- must not reveal private data absent from current viewer’s ViewCommit

# 11. AI Requirements

Implement AI profiles.

AI must handle:
- draft pick
- final character choice
- mark target
- trick use or skip
- dice roll / dice card choice
- property purchase
- score coin placement
- lap reward choice
- burden exchange if implemented

AI policy:
- random: random legal choice
- balanced: reasonable general choice
- aggressive: prefers rent, stealing, acquisition, monopoly
- defensive: prefers cash, safe choices, avoiding bankruptcy

AI should use the same legal prompt choices as human players.

# 12. Testing Requirements

Engine tests:
- board generation
- movement wraparound
- property purchase
- rent payment
- bankruptcy
- weather effect
- fortune effect
- trick effect
- character priority
- character draft
- mark target resolution
- scoring

Backend tests:
- create session
- join session
- start session
- WebSocket connection
- prompt creation
- valid decision
- stale decision
- duplicate decision
- AI decision
- view_commit generation
- replay export

Frontend tests:
- board projection
- prompt target mapping
- tile click without prompt does not submit
- valid prompt target focuses
- unknown prompt remains 2D-only
- private state not rendered for spectator
- reconnect static render behavior

3D tests:
- `projectTileTo3DPosition(0)` = front-left corner
- `projectTileTo3DPosition(10)` = front-right corner
- `projectTileTo3DPosition(20)` = back-right corner
- `projectTileTo3DPosition(30)` = back-left corner
- tile 39 adjacent to tile 0 path
- non-40 tile count fails loudly
- pawn slot ordering stable by player_id
- score coin visual cap at 3

E2E smoke test:
- create 1 human + 3 AI session
- start game
- render 3D board
- receive first prompt
- submit legal choice
- pawn moves
- view_commit updates
- game can progress at least 3 turns

# 13. Implementation Phases

Implement in phases.

## Phase 1 — Scaffolding

- create monorepo
- configure Python backend
- configure React/Vite frontend
- configure Docker Compose
- add Redis
- add README
- add docs

## Phase 2 — Engine MVP

- models
- board
- players
- character cards
- weather cards
- fortune cards
- trick cards
- movement
- property purchase/rent
- bankruptcy
- scoring
- deterministic seed
- engine tests

## Phase 3 — Backend Runtime

- FastAPI app
- session lifecycle
- Redis store
- runtime service
- prompt service
- WebSocket stream
- view_commit projection
- AI decisions
- backend tests

## Phase 4 — 3D Frontend MVP

- lobby
- session creation
- WebSocket stream client
- state store
- 3D board
- 3D tile projection
- pawns
- ownership markers
- score coins
- prompt overlay
- tile inspection
- safe prompt target focus
- movement animation

## Phase 5 — Full Playable Loop

- 1 human + AI game
- 4 human local browser flow if practical
- game-over screen
- scoring breakdown
- E2E smoke test
- documentation pass

# 14. Documentation Deliverables

Create:

- README.md
  - install
  - run backend
  - run frontend
  - run Docker Compose
  - run tests
  - start a game

- docs/Game-Rules.md
  - game components
  - setup
  - round flow
  - turn flow
  - cards
  - characters
  - scoring

- docs/Architecture.md
  - engine/backend/frontend responsibilities
  - authoritative state rules
  - AI flow
  - Redis usage

- docs/API.md
  - REST endpoints
  - WebSocket messages

- docs/Runtime-Contract.md
  - ViewCommit
  - PromptEnvelope
  - DecisionMessage
  - DecisionAck

- docs/3D-Board-Rendering-Contract.md
  - coordinate system
  - tile projection
  - camera defaults
  - object placement

- docs/3D-Interaction-And-Prompt-Mapping.md
  - prompt target mapping
  - click behavior
  - invalid click rules

- docs/3D-Visibility-And-Animation-Rules.md
  - private visibility
  - reconnect behavior
  - animation authority

# 15. Important Exclusions

Do not implement these in MVP:

- mobile-specific UI
- WebXR
- physics engine
- GLB character models
- cinematic camera system
- advanced particle effects
- real authentication
- monetization
- matchmaking
- persistent accounts
- ranked mode
- localization beyond Korean labels and English internal IDs

# 16. Final Deliverable

When complete, provide:

1. file tree
2. summary of implemented features
3. run instructions
4. test instructions
5. known limitations
6. screenshots are optional; code and tests are required
7. next recommended tasks

Build the smallest complete playable 3D MVP first.
Prefer correct gameplay state over visual polish.
Prefer backend-authoritative correctness over frontend convenience.
Prefer primitive 3D readability over heavy art.
```

## Notes

This prompt is intentionally broader than the existing-repository 3D board contracts. It should be used for a fresh project where the game engine, backend, frontend, runtime contracts, and 3D scene all need to be created together.

For existing Project-MRN work, prefer the narrower branch docs:

- `[PLAN]_3D_BOARD_RENDERING_CONTRACT.md`
- `[PLAN]_3D_INTERACTION_AND_PROMPT_MAPPING.md`
- `[PLAN]_3D_VISIBILITY_AND_ANIMATION_RULES.md`
