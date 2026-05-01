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
- A later 2H+2AI continuation reached round 2 after AI P3/P4 auto-play, proving Redis kept authoritative player positions and trick counts across humans and AIs. `current_state` and `view_state:player:*` agreed on P1/P2/P3/P4 pawn positions and hand counts.
- That same continuation exposed a new lifecycle/display failure: P1 round 2 turn 5 emitted repeated movement prompts (`r2:t5:p1:movement:16` down through `movement:3`) with mixed accepted and `already_resolved` acknowledgements. A reroll-capable card such as `뭔칙휜` may create additional movement decisions, but the visible prompt count must be bounded by the rule and older movement prompts must be superseded when a newer same-player/same-turn movement prompt is issued.
- The final P1 screen also showed a consumed `뭔칙휜` in the bottom trick tray while Redis and the player panel both reported P1 `trick_hand: 0` / `Trick0`. State storage was correct; the frontend projection/render path still allowed stale hand UI to survive prompt replay.
- A later frozen P2 screen was caused by backend timeout fallback emitting an illegal movement `choice_id` (`timeout_fallback`) when the prompt had no explicit fallback/default choice. Redis correctly preserved and replayed that bad command; it was not a Redis timing bug. Timeout fallback must pick an explicit default or the first legal prompt choice, and test coverage must assert movement fallback records a legal choice such as `dice`.
- A near-frozen P1 round 2 screen was caused by command wakeup replaying stale `decision_resolved` commands that did not match the current `waiting_prompt_request_id`. Redis was only storing the command stream; the backend wakeup worker must skip mismatched waiting-input commands and advance its consumer offset instead of rehydrating the same prompt over and over.
- A hidden-trick selection regression looked like a UI hand-count problem, but the root cause was a mid-turn continuation boundary. `hidden_trick_card` is emitted after the used trick has already mutated state; resuming from that prompt must enqueue a continuation action instead of replaying the whole turn from the start. Redis `current_state` correctly held `hidden_trick_deck_index`, but the selector also had to consume direct `trick_window_closed` hand fields (`public_tricks`, `hidden_trick_count`, `hand_count`) so projected `view_state` matched the authoritative state.
- Docker compose server/worker containers are image-based and do not mount backend source. After a backend fix, a local green unit test is not enough for browser validation; rebuild and restart `server`, `prompt-timeout-worker`, and `command-wakeup-worker` before judging the screen.
- In the fresh 2-human + 2-AI retest, session `sess_CrAt2zEMf9W79JjFauDvHDf7` no longer showed the stale-command event flood. After P1 accepted the blocking burden exchange, AI turns advanced to round 2, and the stream stayed stable at the active human purchase prompt (`latest_seq: 206`) after repeated waits.
- The same retest showed why the screen can still feel frozen: P4's AI `아주 큰 화목 난로` caused a P1 burden exchange before the source trick/effect was visible to P1, and the round 2 weather removed P1 burden cards while dropping cash from 18 to 10 before the next trick prompt without a durable weather/result explanation in the decision area. Backend state was correct; causal readability was not.
- Weather and AI-triggered side effects must be treated as prompt blockers with mandatory cause context. If an effect creates an immediate human follow-up prompt (`burden_exchange`, purchase, reward choice, etc.), that prompt must include or sit beside the source effect name and resource delta so the player does not interpret the screen as stalled.
- Supply/burden exchange replay must freeze the set of burden cards that were eligible at the start of the supply action. Tracking only `processed_burden_deck_indices` is not enough: if another player's prompt pauses the action and the turn later replays, newly drawn burdens can be pulled into the same threshold chain and send the UI back to an earlier player's burden prompt. Redis preserves the replay command faithfully; the backend action payload must carry `eligible_burden_deck_indices_by_player`.
- A Docker or host memory failure can mimic a frontend freeze. If the page reports `ERR_CONNECTION_REFUSED` for `9090` and `docker compose ps` cannot connect to `/Users/sil/.docker/run/docker.sock`, treat it as runtime infrastructure loss first, not a game-rule regression.
- A post-restart frozen-looking P1 screen was caused by `/runtime-status` returning the public recovery `view_state` even when the caller supplied a valid seat token. On reload, the frontend seeded itself from a recovery payload with no private active prompt or hand tray, while Redis stream history still contained the correct P1 `trick_to_use` prompt. Recovery endpoints must rebuild `view_state` for the authenticated `ViewerContext` from stream history rather than trusting a generic/public cached projection.
- Freshness metadata can be correct for the wrong viewer. A projected view cache at the latest sequence is not sufficient if it was produced for public recovery and later served to a seat. Viewer-specific recovery should either key strictly by viewer or force a rebuild before hydrating a reconnecting player.
- The 1-human + 3-AI full-game replay exposed a different frozen-looking reload path: `/replay` projected each event by re-reading the full Redis stream and rebuilding view state for that prefix. A finished game with 881 stream entries made replay slow enough to block follow-up recovery reads, so the browser sat on board hydration. Replay export must take one stream snapshot, redact messages in memory, and attach the latest view state once instead of doing per-event full-history projection.
- A finished-session reload now restores the board and players, but the screen still lacks a strong game-end state; it can show the final board with a stale-looking actor headline such as `P2's turn`. Full-game screen verification should separately assert a visible `game_end` or results affordance, not only `runtime.status == finished`.
- Memory-aware browser QA must use one browser context per checkpoint and close it immediately. Long playtests should rely on API polling between human prompts, not many persistent tabs, and the dev server/test browser processes must be stopped at the end of the run.

## Regression Tests Added

- `SessionService` store-backed stale-reader tests cover deleted sessions and stale create-session resurrection.
- `RuntimeService` Redis-backed status test covers missing Redis status keys ignoring stale local `waiting_input`.
- Redis realtime store coverage now asserts that checkpoint-only state keeps `players[].position`, `players[].trick_hand`, `players[].hidden_trick_deck_index`, and trick effect flags while projected public view state keeps visible trick counts and board pawn positions.
- `PromptService` coverage now asserts that a newer same-session/same-player prompt supersedes an older pending prompt in both memory-backed and Redis-backed stores, while prompts for other players remain pending.
- Server reveal selector coverage now includes `trick_used`, `lap_reward_chosen`, and `game_end`.
- Web selector coverage now keeps `trick_used` and `game_end` in current-turn reveals when backend projection is absent.
- `CommandStreamWakeupWorker` coverage now asserts that stale waiting-input commands for a different request id are skipped while the active prompt command still wakes runtime processing.
- `RuntimeService` coverage now asserts that pending `hidden_trick_card` replay first replays the prior `trick_to_use` prompt and then resolves the hidden selection with the original stable request id.
- `GPT/test_rule_fixes.py` coverage now asserts that supply replay does not process burden cards drawn after the supply threshold chain started.
- Session API coverage now asserts that authenticated `/runtime-status` recovery returns the seat-specific active prompt and hand tray instead of the public recovery projection.
- Session API coverage now asserts that replay export does not call the expensive per-message projection path and still attaches the latest `view_state`.
- `StreamService` coverage now asserts that forced viewer rebuild ignores a fresh-but-wrong cached projection and restores the active private prompt from stream history.

## Playtest Rule

- A 4-human browser playtest must use four independent browser contexts/tokens and assert both stream legality and visible UI state.
- API-only completion is not a pass. The pass condition is: one full game reaches `game_end`, the board remains visible, and all public-effect families (`운수`, `잔꾀`, `날씨`) produce readable visible feedback during play.
- For faster regression loops, a 2-human + 2-AI session is acceptable only if it explicitly verifies immediate UI deltas for hand removal, shard gain, money loss/gain, weather context, and passive reward bonuses. It does not replace the full 4-human end-to-end pass.
