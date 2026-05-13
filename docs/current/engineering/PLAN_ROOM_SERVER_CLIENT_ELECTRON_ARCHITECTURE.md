# Room, Server, Client, Electron Architecture

Status: ACTIVE  
Updated: 2026-05-05

## 1. Layers

- Engine: owns rules, module frames, prompts, state mutation, and stream event intent.
- Server: owns room/session lifecycle, Redis checkpoints, command validation, stream publication, and WebSocket fanout.
- Web client: renders stream state and submits decisions with the active prompt contract.
- Electron shell: hosts the web client and provides desktop packaging only.

## 2. Command Path

Frontend decisions are requests, not authority.

`apps/web` sends the selected `choice_id` with the active prompt fields:

- `request_id`
- `request_type`
- `player_id`
- `frame_id`
- `module_id`
- `module_type`
- `module_cursor`

`apps/server` accepts the command only when it matches the Redis checkpoint. The engine then resumes the saved module cursor and returns the next transition or prompt.

## 3. Stream Path

The engine emits semantic events through the runtime stream sink. The server validates each event against the active frame/module and publishes an ordered WebSocket message.

The frontend consumes the ordered stream and derives UI state. It does not create game transitions locally.

## 4. Restart Path

Workers can stop and restart at prompt boundaries. Restart loads Redis state, frame stack, module cursor, active prompt data, and stream watermark, then continues from the saved boundary.

## 5. Invalid Conditions

The server rejects:

- duplicate decisions for a completed prompt
- mismatched continuation data
- commands from inactive players
- stream events emitted from the wrong module context
- action types without native module handlers

## 6. Verification

Required coverage:

- server prompt continuation tests
- runtime semantic guard tests
- WebSocket stream selector tests
- reconnect/restart tests
- frontend duplicate-submit tests
