# React Component Structure Spec

Canonical document path. Mirror in `PLAN/[PLAN]_REACT_COMPONENT_STRUCTURE_SPEC.md` is kept only for legacy links.

Status: `ACTIVE`  
Owner: `GPT`  
Updated: `2026-03-31`  
Parent: `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`

## Purpose

Define the frontend component tree, responsibilities, and component-level contracts for the React online game client.

This is a structure specification, not visual design artwork.

## Frontend Module Layout

```text
apps/web/src/
  app/
    App.tsx
    routes.tsx
    providers/
      AppProviders.tsx
      DIProvider.tsx
      ThemeProvider.tsx
  core/
    di/
      container.ts
      tokens.ts
    contracts/
      api.ts
      stream.ts
      prompt.ts
  domain/
    model/
      game.ts
      player.ts
      tile.ts
      prompt.ts
    store/
      gameStateSlice.ts
      promptSlice.ts
      uiSlice.ts
      networkSlice.ts
    selectors/
      boardSelectors.ts
      playerSelectors.ts
      promptSelectors.ts
  infra/
    api/
      SessionApiClient.ts
    ws/
      StreamClient.ts
    adapters/
      DecisionSubmitter.ts
  features/
    lobby/
    board/
    players/
    timeline/
    theater/
    prompt/
    status/
    replay/
  shared/
    ui/
    utils/
apps/web/tests/
```

## App-Level Layout

Top-level shell:

- `TopBar`: session id, round/turn, connection state
- `MainBoardArea`: board + theater + incident cards
- `RightRail`: player panels + situation panel
- `BottomRail`: timeline and event feed
- `PromptOverlay`: active human choice UI (collapsible)

Mobile adaptation:

- board-first viewport
- right rail collapses into tabbed drawer
- prompt overlay becomes bottom sheet

## Route Structure

- `/` lobby page
- `/session/:sessionId/live` live match (player or spectator)
- `/session/:sessionId/replay` replay timeline mode

## Feature Components

## 1. Lobby

Primary components:

- `LobbyPage`
- `SessionCreateForm`
- `SeatConfigMatrix`
- `JoinByTokenForm`
- `SessionListPanel`

Responsibilities:

- create/join/start session
- validate seat composition (human/AI)
- surface host/start constraints

## 2. Board

Primary components:

- `BoardStage`
- `TileGrid`
- `TileCell`
- `PawnLayer`
- `RouteAnimationLayer`
- `IncidentCardStack`

Responsibilities:

- render topology from `parameter_manifest.board`
  - default profile may be 40-tile ring
  - contract must not assume fixed tile count
- render ownership and tile economy metadata
- render pawn positions and move path
- show board-near incident cards

## 3. Player Panels

Primary components:

- `PlayersRail`
- `PlayerCard`
- `PlayerEconomyRow`
- `PlayerEffectsRow`
- `DiceCardRow`

Responsibilities:

- per-player public state visibility:
  - cash, shards, score tokens, owned tiles
  - public tricks + hidden trick count
  - burdens summary
  - eliminated status and current tile
  - remaining dice cards
- seat/player list must be data-driven from manifest/session snapshot
  - no fixed 4-card layout assumption in component contracts

## 4. Timeline and Theater

Primary components:

- `TimelinePanel`
- `TimelineEventRow`
- `TheaterPanel`
- `ActionTicker`
- `EconomyDeltaCard`

Responsibilities:

- show ordered public event history
- summarize non-human turns in theater style
- keep economy deltas visible and scannable

## 5. Prompt UX

Primary components:

- `PromptOverlay`
- `PromptHeader`
- `PromptChoiceGrid`
- `PromptChoiceCard`
- `PromptFooter`
- `PromptBusyMask`
- `PromptCollapseToggle`

Responsibilities:

- display one prompt at a time
- full-card click targets
- human-readable title/effect text
- countdown and pending state
- lock only after user click
- collapse/restore interaction

## 6. Status and Diagnostics

Primary components:

- `SituationPanel`
- `NetworkBadge`
- `RuntimeAlertStack`

Responsibilities:

- weather, marker owner, end-time meter
- connection/retry status
- bankruptcy/endgame/public alerts

## Component Contract Patterns

## Container vs Presenter

- Container components:
  - read selectors
  - dispatch domain actions
  - inject ports from DI.
- Presenter components:
  - no direct infra access
  - receive typed props
  - pure rendering + UI callbacks only.

## Prop Contract Example

```ts
type PromptChoiceCardProps = {
  choiceId: string;
  title: string;
  description: string;
  tags: string[];
  disabled: boolean;
  hidden?: boolean;
  onSelect: (choiceId: string) => void;
};
```

## Event Contract Example

```ts
type PromptOverlayEvents = {
  onChoiceSelect: (choiceId: string) => void;
  onCollapse: () => void;
  onRestore: () => void;
  onCloseSpectatorView: () => void;
};
```

## Data and Selector Boundaries

Required selectors:

- `selectBoardTiles()`
- `selectPawnPositions()`
- `selectCurrentActor()`
- `selectSituationSummary()`
- `selectPlayerCards()`
- `selectPromptViewModel()`
- `selectTheaterCards()`

Rules:

- selectors compute derived display models
- no reducer logic in components
- no direct event parsing in components
- no fixed-size assumptions in selectors (tile count, seat count, dice value range)
- selectors should consume stable IDs and resolve display labels via catalog/fallback layer
- selectors/components should observe manifest lifecycle (`manifest_hash`) and rehydrate derived caches on change

## Accessibility and Interaction Rules

- Every choice card is keyboard focusable.
- `Enter` and `Space` trigger the same handler as click.
- Prompt focus returns to previously focused element after close.
- Busy state exposes `aria-busy=true`.
- Collapsed prompt remains accessible via fixed toggle.

## Animation Rules

- Pawn movement:
  - event-driven, path-based, interrupt-safe.
- Incident cards:
  - fade-in near board center, auto-dismiss.
- Marker transfer:
  - source and target player highlight pulse.
- Bankruptcy:
  - player panel state changes to `OUT` with one-time alert.

## Test Matrix

Unit tests:

- `PromptChoiceCard.spec.tsx` full-card click and keyboard
- `PlayerCard.spec.tsx` visibility and hidden counts
- `TileCell.spec.tsx` ownership and pricing labels

Integration tests:

- prompt lifecycle (`open -> submit -> ack -> close`)
- theater feed updates while prompt collapsed
- reconnect and state continuity
- variant topology render continuity (non-default tile count fixture)
- variant seat-count render continuity (non-default seat fixture)

E2E tests:

- human seat full turn (draft, trick, movement, purchase)
- non-human turn observability while no prompt active
- prompt collapse and restore while other players act

## Documentation Rule

When adding/changing a component:

1. Update this spec section and component list.
2. Add or update the test matrix row.
3. Update related interface/API docs if data shape changed.
4. If any fixed-size literal is introduced (e.g., seat/tile count), annotate it as `default-profile` and document fallback path.
