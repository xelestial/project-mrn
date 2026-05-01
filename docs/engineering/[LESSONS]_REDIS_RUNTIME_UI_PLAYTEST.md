# Redis Runtime UI Playtest Lessons

Date: 2026-05-01

## Authoritative Store Boundary

- In Redis-backed mode, Redis is the authoritative hot-state store. Process-local dictionaries are caches only.
- If a Redis-backed runtime status key is missing, backend readers must not fall back to stale process memory. Missing Redis runtime state means idle/absent state unless a live task in the same process proves otherwise.
- Store-backed session reads must refresh from the shared session store before returning public session state. Otherwise an API process can keep showing a deleted or archived session after the archive worker has already removed the Redis hot keys.
- Store-backed session creation must refresh before persisting. A stale process that creates a new session after cleanup can otherwise resurrect deleted sessions because the whole session set is persisted together.

## Worker And API Ownership

- Redis timing was not the root cause of the archived-session regression. The bug lived in backend ownership boundaries: API and worker processes were allowed to use their own old memory after another backend process had changed the shared state.
- Long-lived workers may cache for performance, but every active-session scan and every public read path must re-check the shared store when Redis persistence is enabled.
- Archive cleanup must be tested against at least two backend service instances or an equivalent stale-reader harness, not just the worker process that performed the cleanup.

## Screen-Visible Game Rules

- Rule events are not complete unless the player can see the effect on screen. `운수`, `잔꾀`, and `날씨` effects that mutate public state must surface as readable overlay/reveal items, not only as later board changes.
- Public hidden-card counts must be derived from an actual hidden card identity. If `hidden_trick_deck_index` is absent or no longer matches a card in `trick_hand`, selectors must expose `hidden_trick_count: 0`; otherwise the UI can claim a hidden trick exists while every card is public.
- Backend `view_state.reveals` is authoritative for the frontend when present. It must include every high-signal public effect that the fallback selector would otherwise show: `weather_reveal`, `trick_used`, `fortune_resolved`, `lap_reward_chosen`, `bankruptcy`, and `game_end`.
- `game_end` needs both a stream event and an explicit visual overlay/result state. A finished backend status alone is not enough for screen verification.
- Labels must communicate hard rule constraints. Lap reward copy now says the budget must be spent exactly, because a disabled confirm button at `9/10` looked like a UI bug without that rule text.

## Regression Tests Added

- `SessionService` store-backed stale-reader tests cover deleted sessions and stale create-session resurrection.
- `RuntimeService` Redis-backed status test covers missing Redis status keys ignoring stale local `waiting_input`.
- Redis realtime store coverage now asserts that checkpoint-only state keeps `players[].position`, `players[].trick_hand`, `players[].hidden_trick_deck_index`, and trick effect flags while projected public view state keeps visible trick counts and board pawn positions.
- Server reveal selector coverage now includes `trick_used`, `lap_reward_chosen`, and `game_end`.
- Web selector coverage now keeps `trick_used` and `game_end` in current-turn reveals when backend projection is absent.

## Playtest Rule

- A 4-human browser playtest must use four independent browser contexts/tokens and assert both stream legality and visible UI state.
- API-only completion is not a pass. The pass condition is: one full game reaches `game_end`, the board remains visible, and all public-effect families (`운수`, `잔꾀`, `날씨`) produce readable visible feedback during play.
