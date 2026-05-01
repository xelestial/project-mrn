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
- UI verification must check causal readability, not just final state. A test is incomplete if it only proves that cash, shards, hand count, or position eventually changed; it must also prove that the screen explains why the change happened at the moment of the effect.
- `잔꾀` use must visibly remove the used card from the hand/tray immediately, update public/hidden hand counts, and show the effect label/result before the next decision can visually dominate the screen.
- `운수` results that change money, shards, movement, or bankruptcy risk must leave a readable reveal/feed item long enough for the player to connect the card to the resource delta. A later cash total alone is not acceptable evidence.
- Character passive bonuses such as `객주` lap reward enhancement need their own visible breakdown or a combined reward line that shows base reward plus bonus. Applying the bonus silently in backend state makes the rule feel invisible even when the math is correct.
- Weather must remain visible as current round context during decisions and effect resolution. If weather changes resource or marker behavior, the UI needs a named weather line rather than only a generic round/turn header.
- Public hidden-card counts must be derived from an actual hidden card identity. If `hidden_trick_deck_index` is absent or no longer matches a card in `trick_hand`, selectors must expose `hidden_trick_count: 0`; otherwise the UI can claim a hidden trick exists while every card is public.
- Backend `view_state.reveals` is authoritative for the frontend when present. It must include every high-signal public effect that the fallback selector would otherwise show: `weather_reveal`, `trick_used`, `fortune_resolved`, `lap_reward_chosen`, `bankruptcy`, and `game_end`.
- `game_end` needs both a stream event and an explicit visual overlay/result state. A finished backend status alone is not enough for screen verification.
- Labels must communicate hard rule constraints. Lap reward copy now says the budget must be spent exactly, because a disabled confirm button at `9/10` looked like a UI bug without that rule text.

## 2026-05-01 2H+2AI UI/UX Finding

- A fast 2-human + 2-AI playtest confirmed that using `무료 증정` removes it from P1's hand immediately and reduces the visible hand count from 5 to 4.
- Earlier 2H+2AI evidence confirmed that `거대한 산불` immediately removed the trick card and raised shards from 4 to 6.
- The remaining UX gap is not final-state correctness. It is effect attribution: `운수` cash loss and `객주` reward enhancement can be mathematically correct while still being hard for a player to perceive.
- Treat every effect family (`잔꾀`, `운수`, `날씨`, character passive bonuses) as requiring a visible cause-and-effect artifact: overlay, reveal panel, action feed line, or prompt-local result summary.
- A stale `hidden_trick_card` pending prompt was observed after a visible trick use path. Even when the foreground UI looks correct, stale pending prompts should be considered a UX risk because they can later surface as confusing prompts or turn stalls.
- Redis was not the owner of that stale-prompt bug; it only preserved what the backend wrote. The backend prompt lifecycle must guarantee at most one active pending prompt per `(session_id, player_id)` and mark older same-player prompts as `superseded` when a newer prompt is created.

## Regression Tests Added

- `SessionService` store-backed stale-reader tests cover deleted sessions and stale create-session resurrection.
- `RuntimeService` Redis-backed status test covers missing Redis status keys ignoring stale local `waiting_input`.
- Redis realtime store coverage now asserts that checkpoint-only state keeps `players[].position`, `players[].trick_hand`, `players[].hidden_trick_deck_index`, and trick effect flags while projected public view state keeps visible trick counts and board pawn positions.
- `PromptService` coverage now asserts that a newer same-session/same-player prompt supersedes an older pending prompt in both memory-backed and Redis-backed stores, while prompts for other players remain pending.
- Server reveal selector coverage now includes `trick_used`, `lap_reward_chosen`, and `game_end`.
- Web selector coverage now keeps `trick_used` and `game_end` in current-turn reveals when backend projection is absent.

## Playtest Rule

- A 4-human browser playtest must use four independent browser contexts/tokens and assert both stream legality and visible UI state.
- API-only completion is not a pass. The pass condition is: one full game reaches `game_end`, the board remains visible, and all public-effect families (`운수`, `잔꾀`, `날씨`) produce readable visible feedback during play.
- For faster regression loops, a 2-human + 2-AI session is acceptable only if it explicitly verifies immediate UI deltas for hand removal, shard gain, money loss/gain, weather context, and passive reward bonuses. It does not replace the full 4-human end-to-end pass.
