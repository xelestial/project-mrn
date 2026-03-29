# [PLAN] Online Game Interface Spec

Status: `ACTIVE`  
Owner: `Shared`  
Updated: `2026-03-29`  
Parents:
- `PLAN/REACT_ONLINE_GAME_IMPL_PLAN.md`
- `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`

## Purpose

Define the DI-facing interfaces between backend runtime services and frontend application ports.

This document stabilizes seams for:

- testability
- ownership split
- future client replacement (Unity/web/mobile)

## Boundary Principles

- Engine rules are backend-only.
- Interfaces expose public data only.
- Frontend never imports backend internals.
- Backend route handlers depend on service interfaces, not concrete runtime classes.

## Backend Service Interfaces

## SessionService

Responsibilities:

- create, join, start, inspect sessions
- enforce session state transitions

Python protocol sketch:

```py
class SessionService(Protocol):
    def create_session(self, req: CreateSessionRequest) -> SessionView: ...
    def list_sessions(self) -> list[SessionView]: ...
    def get_session(self, session_id: str) -> SessionView: ...
    def join_session(self, req: JoinSessionRequest) -> JoinResult: ...
    def start_session(self, req: StartSessionRequest) -> SessionView: ...
```

## RuntimeService

Responsibilities:

- run/stop engine loops per session
- serialize event dispatch to broadcaster

```py
class RuntimeService(Protocol):
    def start_runtime(self, session_id: str) -> None: ...
    def stop_runtime(self, session_id: str, reason: str) -> None: ...
    def runtime_status(self, session_id: str) -> RuntimeStatus: ...
```

## PromptService

Responsibilities:

- register prompt pending state
- validate and consume decisions
- enforce timeout fallback

```py
class PromptService(Protocol):
    def create_prompt(self, prompt: PromptEnvelope) -> None: ...
    def submit_decision(self, req: DecisionMessage) -> DecisionAck: ...
    def timeout_pending(self, now_ms: int) -> list[TimeoutResult]: ...
```

## StreamService

Responsibilities:

- emit ordered `seq` messages
- serve replay window for `resume(last_seq)`

```py
class StreamService(Protocol):
    def publish(self, session_id: str, message: StreamMessage) -> int: ...
    def replay_from(self, session_id: str, last_seq: int) -> list[StreamMessage]: ...
    def subscribe(self, session_id: str, conn_id: str) -> None: ...
    def unsubscribe(self, session_id: str, conn_id: str) -> None: ...
```

## AuthService

Responsibilities:

- validate host and seat tokens
- enforce role (`host`, `seat`, `spectator`)

```py
class AuthService(Protocol):
    def issue_join_tokens(self, session_id: str, seats: list[int]) -> dict[int, str]: ...
    def verify_token(self, token: str, session_id: str) -> AuthContext: ...
```

## Frontend Port Interfaces

## SessionApiPort

Responsibilities:

- call REST session endpoints

```ts
export interface SessionApiPort {
  createSession(req: CreateSessionRequest): Promise<ApiEnvelope<CreateSessionResponse>>;
  listSessions(): Promise<ApiEnvelope<ListSessionsResponse>>;
  getSession(sessionId: string): Promise<ApiEnvelope<SessionView>>;
  joinSession(sessionId: string, req: JoinSessionRequest): Promise<ApiEnvelope<JoinSessionResponse>>;
  startSession(sessionId: string, req: StartSessionRequest): Promise<ApiEnvelope<SessionView>>;
}
```

## StreamPort

Responsibilities:

- manage WS connection, heartbeat, resume

```ts
export interface StreamPort {
  connect(params: StreamConnectParams): Promise<void>;
  disconnect(): Promise<void>;
  sendDecision(message: DecisionMessage): Promise<void>;
  sendResume(lastSeq: number): Promise<void>;
  onMessage(handler: (message: StreamInboundMessage) => void): void;
  onStatus(handler: (status: NetworkStatus) => void): void;
}
```

## PromptCoordinatorPort

Responsibilities:

- map prompt envelopes to local prompt view models
- lock/ack lifecycle

```ts
export interface PromptCoordinatorPort {
  openPrompt(prompt: PromptEnvelope): void;
  markPending(requestId: string): void;
  closePrompt(requestId: string): void;
  rejectPrompt(requestId: string, reason: string): void;
}
```

## TheaterFeedPort

Responsibilities:

- summarize non-human events for theater cards

```ts
export interface TheaterFeedPort {
  append(event: VisEventEnvelope): void;
  list(limit: number): TheaterCardViewModel[];
}
```

## Core Shared Data Interfaces

## StreamInboundMessage

```ts
type StreamInboundMessage =
  | { type: "event"; seq: number; session_id: string; payload: VisEventEnvelope }
  | { type: "prompt"; seq: number; session_id: string; payload: PromptEnvelope }
  | { type: "decision_ack"; seq: number; session_id: string; payload: DecisionAck }
  | { type: "error"; seq: number; session_id: string; payload: ApiErrorPayload }
  | { type: "heartbeat"; seq: number; session_id: string; payload: HeartbeatPayload };
```

## PromptEnvelope

Mandatory fields:

- `request_id`
- `request_type`
- `player_id`
- `timeout_ms`
- `fallback_policy`
- `choices[]`
- `public_context`

## DecisionMessage

Mandatory fields:

- `request_id`
- `player_id`
- `choice_id`
- `client_seq` (last applied seq on client side)

Optional:

- `choice_payload` for typed prompt decisions.

## Request Type to Choice Payload Mapping

| request_type | choice_payload schema |
|---|---|
| `draft_card` | `{ card_id: string }` |
| `final_character_choice` | `{ character_id: string }` |
| `trick_to_use` | `{ trick_id: string \| "skip" }` |
| `movement` | `{ mode: "roll" \| "dice_card", dice_cards?: number[] }` |
| `purchase_tile` | `{ buy: boolean }` |
| `mark_target` | `{ target_player_id?: number, target_character_id?: string, no_target?: boolean }` |
| `active_flip` | `{ flip_from?: string, flip_to?: string, finish?: boolean }` |
| `burden_exchange` | `{ selected_burdens: string[] }` |
| `lap_reward` | `{ reward: "cash" \| "shard" \| "score" }` |
| `runaway_step_choice` | `{ mode: "safe_tile" \| "bonus_tile" }` |

## DI Binding Rules

Backend composition root:

- `app.py` binds protocols to concrete services.

Frontend composition root:

- `AppProviders.tsx` binds ports:
  - `SessionApiPort -> SessionApiClient`
  - `StreamPort -> StreamClient`
  - `PromptCoordinatorPort -> PromptCoordinator`
  - `TheaterFeedPort -> TheaterFeedStore`

## Error Interface

`ApiErrorPayload` fields:

- `code`
- `message`
- `retryable`
- `request_id?`
- `details?`

Canonical codes:

- `UNAUTHORIZED_SEAT`
- `SESSION_NOT_FOUND`
- `INVALID_STATE_TRANSITION`
- `STALE_REQUEST_ID`
- `PROMPT_TIMEOUT`
- `DECISION_REJECTED`
- `RESUME_GAP_TOO_OLD`
- `INTERNAL_SERVER_ERROR`

## Compatibility Policy

- Contract changes are additive by default.
- Removal/rename requires:
  1. migration window with aliases
  2. parser tests updated for both forms
  3. explicit note in `PLAN/SHARED_VISUAL_RUNTIME_CONTRACT.md`.

## Verification Checklist

For each interface change:

1. Protocol/Type interface updated.
2. Adapter implementation updated.
3. Unit tests updated.
4. Integration test covers success and failure path.
5. API spec and execution plan updated.
