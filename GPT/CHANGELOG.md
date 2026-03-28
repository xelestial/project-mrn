## v0.7.66-ai-log-driven-tuning (2026-03-29)
- Used `ai_decisions.jsonl` analysis to tune GPT decision nodes instead of only reading end-game summaries.
- Reduced over-eager rescue/marker weighting in draft/final character choice by removing extra off-marker-owner bonus and narrowing which character families receive survival-first marker amplification.
- Softened the GPT-only cleanup purchase soft-block thresholds so moderate cleanup pressure no longer suppresses as many otherwise survivable land buys.
- Added regression coverage for the new marker-bonus ownership rule and for the final-character path so `만신`-style marker rescue bias does not get unintentionally over-amplified again.

## v0.7.65-ai-analysis-log (2026-03-29)
- Finished the AI-improvement pass by exporting per-decision analysis rows into `ai_decisions.jsonl` alongside `games.jsonl` / `errors.jsonl`.
- AI decision export now captures the canonical trace payloads for non-trick decisions plus purchase, lap reward, marker flip, and geo bonus choices with per-game seed/run metadata for offline comparison.
- Chunked batch merge now carries `ai_decisions.jsonl` forward so long-running experiment batches preserve the same analysis stream after merge.

## v0.7.64-ai-trace-complete (2026-03-29)
- Extended the canonical AI decision-trace layer beyond economy choices so draft choice, final character choice, mark target choice, doctrine relief, geo bonus, coin placement, active flip, and burden exchange now all emit the shared `DecisionTrace` payload shape.
- Added structured detector hits for character survival weighting, distress-marker rescue value, public-mark ambiguity/confidence, cleanup-driven geo cash pressure, token-placement windows, flip denial / money-relief signals, and burden-exchange safety guards.
- Unified runtime debug output around the same `features -> detector_hits -> effect_adjustments -> final_choice` contract across the full first-pass non-trick decision surface.
- Added regression coverage for the newly traced decision families and reran 30-game / 100-game `heuristic_v3_gpt` smoke batches without runtime crashes.

## v0.7.63-ai-trace (2026-03-29)
- Added shared AI decision-trace substrate in `policy/pipeline_trace.py` so detector hits, feature snapshots, and final choices can be serialized in a consistent shape.
- Purchase decisions now emit structured trace payloads, including monopoly/denial windows, safe growth buys, token-window redirects, cleanup locks, and hard survival guards.
- Movement decisions now emit structured trace payloads and once again apply turn-intent adjustments (`card_preserve`, lap-engine two-card commitment, leader spike windows) inside the runtime-bridge path.
- Lap reward decisions now emit structured trace payloads with shard checkpoint, cleanup cash pressure, coin-conversion window, and lap-engine signals.
- Added regression coverage for the new trace substrate and ran a 30-game `heuristic_v3_gpt` smoke batch without runtime errors.

## v0.7.62-replay-ui (2026-03-29)
- Added a replay-viewer UI history pass so viewer-facing polish changes are recorded explicitly instead of being hidden inside bug-fix commits.
- Completed the GPT human-play prompt-envelope cleanup so the active runtime now consumes canonical `request_type` / `legal_choices` / `public_context` fields without legacy `type` / `options` mirrors or top-level context flattening.
- Expanded replay event visibility for public match review, including readable `trick_used`, `marker_flip`, weather text, lap-reward amounts, and dice-card usage summaries.
- Reworked replay wording toward human-facing labels: Korean sidebar/status labels, natural event summaries, end-time wording, readable purchase/landing outcomes, and character-name-based draft/final-choice labels.
- Adjusted replay board presentation for readability: hollow-square loop layout, larger pawn markers with player numbers, clearer special-tile labels (`운수`, `종료 - 1`, `종료 - 2`), visible tile color bands, and more readable tile-price wording (`3냥`, `5냥`).
- Improved replay/player panels to show public-vs-hidden trick separation, remaining dice cards, weather descriptions, and other public-state details more clearly.
- Reordered replay frames toward real gameplay flow inside turns and updated intermediate frame state so move, lap-reward, rent, purchase, and dice-card consumption are visible before the next terminal snapshot.
- Brought markdown replay output closer to the HTML viewer by switching it to Korean labels, human-readable event summaries, 1-based tile wording, and clearer public-state tables.
- Started the same human-facing wording pass on the live human-play viewer so the header, status panel, prompt shell, and shared Phase 5 labels are less engine-internal and more player-readable.
- Continued the live Phase 5 wording pass across event labels, player cards, phase strip, turn headers, and board-center status summaries so the spectator/human-play path is less English- and engine-jargon-heavy.

## v0.7.61-auditfix2 (2026-03-27)
- Corrected README baseline values so current runtime defaults now match `ruleset.json` / `GameConfig` (20 cash / 0 hand coins / 4 shards) instead of older experiment presets.
- Added regression coverage that compares runtime-spawned players against injected rule values to catch config/ruleset drift.
- Tightened `heuristic_v3_gpt` around cleanup / reserve stress: stronger anti-growth penalties under distress, earlier cash fallback, and stricter non-blocking land-buy rejection when token windows or cleanup risk are better survival lines.

## 0.7.61
- Stage 4 board/rules separation: board layouts can now use `economy_profile` keys instead of embedding purchase/rent costs.
- `ruleset.json` now owns land profile costs under `economy.land_profiles`.
- Runtime tile state resolves economy profiles through injected `GameRules`, keeping board layout structural and ruleset numeric.

## 0.7.58
- Added `game_rules.py` and `GameRules` injection layer.
- Wired token, lap reward, takeover, force sale, and end condition lookups through injected rules while keeping legacy config fields synchronized.
- Added `test_rules_injection.py`.

## 0.7.48
- Added `event_system.py` and `effect_handlers.py` to decouple core effect execution from `GameEngine`.
- Routed weather round application, fortune draw resolution, tile purchase, rent payment, and tile-based character landing effects through the event dispatcher.
- Added regression tests for event integration and custom handler override points.

## 0.7.45
- Board layout externalization expanded to include board-level metadata through `BoardLayoutMetadata.from_external_dict(...)`.
- `board_layout_creator.py` now supports JSON full layout specs and CSV tile specs with optional sidecar metadata JSON (`*_meta.json` or `--board-layout-meta`).
- Board metadata can now externalize S tile display/probabilities, F1/F2 F gains and shard gains, malicious multiplier, and zone color sequence.
- CLI runners (`simulate_with_logs.py`, `run_chunked_batch.py`) now accept `--board-layout-meta` for CSV-based layouts.

## v0.7.43 (2026-03-25)
- Reworked board generation around cached `TileMetadata` records instead of relying on scattered absolute tile assumptions.
- The default map now uses the 2-3-2 side layout (`5,5 - 3,4,3 - 5,5`) and still expands dynamically into the full loop from side metadata.
- `GameState` now builds mutable `TileState` objects from metadata so tile index, color, purchase cost, rent, owner, and placed score coins can be inspected from a single source of truth while legacy `state.board`, `state.tile_owner`, and `state.tile_coins` access keeps working through views.
- Added dynamic tile-query helpers (`tile_at`, `tile_positions`, `first_tile_position`, `block_tile_positions`, `adjacent_land_positions`) to remove test/runtime dependence on hard-coded board coordinates.
- Updated config/rule tests to resolve tiles by metadata rather than fixed indices.

## v0.7.37 (2026-03-25)
- Retuned `heuristic_v2_control` lap rewards so shard priority remains active in leader emergencies, but stronger cash fallbacks now kick in under stacked low-cash / rent / burden / reserve risk.
- Added regression coverage for the new control lap-reward safety valve: safe leader emergencies still prefer shards, while low-cash stacked-risk states correctly fall back to cash.

## v0.7.35
- Rebalanced `heuristic_v2_control` to reduce overcommitment to costly direct denial and improve pace.
- Added stronger preference for efficient denial (`사기꾼`, `교리 연구관`, `교리 감독관`, `객주`, `탈출 노비`) in leader emergencies.
- Added control-specific penalties for low-cash brute-force denial and a small keep-pace bonus when no leader emergency exists.
- Tweaked control lap-reward evaluation to be less shard-heavy and slightly more coin/cash aware.

# CHANGELOG

## v0.7.34 (2026-03-25)
- Refined non-v1 (`heuristic_v2_*`) marker-control denial so `교리 연구관` / `교리 감독관` can be chosen even when direct denial options exist, when the marker can strip away a leader's most-needed face.
- Added leader-need inference for expansion, mobility / rent escape, and burden relief so marker flips can target cards like `중매꾼` / `건설업자`, `탈출 노비`, or `박수` when those are the leader's best stabilizers.
- Extended marker flip scoring to penalize flips that would feed the leader and reward flips that remove urgent leader-needed faces.
- Added regression tests covering marker bonus with live direct-denial alternatives and targeted marker flips that remove leader escape faces.

## v0.7.33 (2026-03-25)
- Strengthened all non-v1 (`heuristic_v2_*`) character-evaluation profiles to react earlier when an opponent reaches the 6-8 tile danger band or becomes a clear solo leader.
- Added an emergency denial layer that boosts direct disruption characters (`자객`, `산적`, `추노꾼`, `사기꾼`, `박수`, `만신`, `어사`) and deprioritizes pure growth picks when a leader is close to the 9-tile end trigger.
- Extended marker-control fallback so v2 profiles now prefer `교리 연구관` / `교리 감독관` when leader pressure is high and no stronger direct denial option is offered.
- Increased v2 mark-target / flip evaluation bias toward urgent leaders so disruption actions focus more reliably on the player closest to ending the game.

## v0.7.32 (2026-03-25)
- Reintroduced the 9-tile end trigger. Owning 9 tiles now ends the game, but the winner is still decided by total score (placed victory coins + tiles), then tiles, then cash.
- Adjusted AI burden handling so distressed players no longer auto-pay burden exchange at supply when preserving burden-based escape lines is better.
- Added fallback draft/final-pick preference for `교리 연구관` / `교리 감독관` when a player is under survival pressure and direct escape options like `박수`, `만신`, `탈출 노비` are not offered.

## v0.7.31 (2026-03-25)
- Added round-based `[날씨]` system from `weather.csv`.
- Weather draws once per round and affects all alive players for that round.
- Excluded `배신의 징표` for now.
- Added zone color mapping per land block and color-based rent doubling weather.
- Added regression coverage for hunt bonus / cold winter lap block / color rent double / same-tile bonus / unrest bank rent.

v0.7.26 - 2026-03-24
- Added liquidity-risk aware AI evaluation. Character scoring now penalizes cash-dry states and values escape / burden-insurance characters more when next-turn losses are likely.
- Added purchase safety checks so heuristic policies skip non-winning land buys when post-purchase cash would fall below a reserve derived from expected and worst one-turn losses (rent exposure, hunter pull, bandit tax, burden cleanup risk).
- Added regression tests for risk-aware purchase skipping / allowing.

## 0.7.23
- 시작 자금을 50냥으로 상향.
- 랩 현금 보상을 8냥으로 상향.

## 0.7.22
- AI가 박수/만신을 평가할 때 전역 짐 압력(public burden pressure), 공개된 짐 카드 수, 상대 현금을 반영하도록 조정
- 박수는 내 짐을 미리 넘겨 산불/화재 리스크를 줄이는 가치가 커지고, 만신은 공개된 상대 짐을 미리 정리하는 가치가 커짐
- 박수/만신 지목 대상 선택도 visible burden + 상대 현금을 더 강하게 보도록 조정

## 0.7.21
- 잔꾀 손패 공개 규칙 추가: 각 플레이어는 정확히 1장의 잔꾀만 비공개로 유지하고, 나머지는 모두 공개
- AI는 상대 잔꾀를 추론할 때 이제 공개된 잔꾀만 사용
- 엔진 로그/결과 요약에 public_tricks, hidden_trick_count를 추가

## 0.7.20
- 기본 F 종료값을 12에서 15로 상향
- 나머지 기본 조건(시작 40냥, 렌트 1배, 7타일 종료 제거, 9타일/3독점 종료, 아레나 기본)은 유지

## v0.7.18 - 2026-03-24

### Changed
- Kept the existing 7-tile end trigger and added new immediate end checks for 3 monopolized zones and 9 owned tiles.
- Print settings now exposes all configured end thresholds.

### Validation snapshot
- Added regression tests for `THREE_MONOPOLIES`.
- Removed `SEVEN_TILES` and `NINE_TILES` as end conditions and retargeted leader-pressure heuristics to monopoly pressure.
- Verified default config and end-rule priority through unit tests.

# Changelog

## 0.7.17
- 기본 시작 현금을 40냥으로 상향
- 기본 렌트 1배, 랩 현금 4, 악성 토지 벌금 3배, 아레나 기본, 시작 액티브 면 랜덤화는 유지

## 0.7.15
- 8개 캐릭터 카드의 시작 액티브 면을 양면 중 랜덤으로 세팅하도록 변경
- 엔진 RNG를 통해 시드 재현성을 유지하고 `initial_active_faces` 로그 이벤트 추가

- 0.7.13: 기본 시작 현금을 30냥으로 상향하고, 지목 선택을 공개 후보군의 불확실성 기반 확률 추론으로 바꿨다. 후보가 많고 확신이 낮으면 지목을 포기할 수 있어 비정상적으로 높던 지목 성공률을 낮추도록 했다.

- 0.7.12: 빈 땅 도착 시 돈이 모자라면 구매를 스킵하고 파산하지 않도록 수정했다. 이제 파산은 렌트/벌금/강제 지불 비용을 못 냈을 때만 발생한다.

- 0.7.11: 모든 프로파일의 인물 선택 점수에 피지목 리스크를 반영했고, 기본 시작 현금을 20냥으로 하향했으며, 랩 현금 보상을 4냥으로 상향했다.

- 0.7.10: 지목 대상 선택이 상대의 숨겨진 인물 정보를 직접 보지 않도록 수정했고, 지목 성공률을 실제 인물 추측 적중률로 해석할 수 있게 했다.


## v0.7.6
- 기본 시작 현금을 30냥으로 상향
- F 종료값을 12로 변경
- 토지 가격/통행료를 한 변 기준 `(3-4-3)-(5-5)-(3-4-3)` / `(3-4-3)-(5-5)-(3-4-3)`로 변경
- 위치별 토지 가격표를 엔진/정책 조회 경로에 반영

## v0.7.8
- 시작 현금을 40냥으로 상향
- 지목 시도/성공/실패 및 지목 성공률을 strategy_summary, basic_stats, summary.json에 추가
- summary에 1등 평균 랩 수/랩 보상 횟수 필드를 다시 노출

## v0.7.5
- summary.json 및 games.jsonl에 문서 무결성(doc_integrity_ok, checked_pairs) 포함
- AI 정책에 `heuristic_v2_token_opt` 프로파일 추가
- 승리토큰 최적화 전략: 내 타일 도착/텔레포트성 잔꾀/이동 카드 시너지 강화, 승리 임계 근처 리더 견제 반영
- 문서 무결성 검사 모듈/테스트 재통합

# Changelog

## v0.7.7
- Changed malicious-land toll from a flat 8 to 3x the tile face value (purchase price by position).
- Added malicious multiplier and per-side malicious tolls to `print_settings.py`.
- Kept starting cash at 30, F end at 12, and the positional side-price table from v0.7.6.

## 0.7.2
- Updated shard settings to starting shards = 4 and lap shard reward = 3.
- Added print_settings.py to show current simulator settings.
- Added test_config_settings.py to verify config values, initial player shards, and shard lap reward behavior.

## v0.6.6
- 플레이어별 혼합 랩 정책 지원 추가 (`--player-lap-policies`)
- 랩 정책별 승률/점수/현금/배치/조각 평균 집계 추가
- 혼합 랩 정책 비교 스크립트 추가 (`compare_mixed_lap_policies.py`)
- 구역 독점 보호 및 혼합 정책 실험을 위한 시뮬레이션 인자 확장
- 시뮬레이션에 시작 자금 오버라이드 추가 (`--starting-cash`)

## 0.6.5
- Added monopoly protection: fully monopolized zones cannot be taken over by any means, including character skills, fortune cards, or trick-based transfers.
- Added lap reward policy modes: `cash_focus`, `shard_focus`, `coin_focus`, `balanced`, and `heuristic_v1`.
- Added `compare_lap_policies.py` for side-by-side lap policy comparison.

# Changelog

## 0.6.2
- 잔꾀의 전역/개인 통행료 조절 효과를 실제 엔진에 반영
- 재뿌리기/긴장감 조성/마당발/신의뜻/가벼운 분리불안/무역의 선물을 구현
- 같은 칸 도착 시 현금/조각 강탈 계열 잔꾀를 턴 버프로 연결
- 뇌고왕(오탈자 뇌절왕 포함)을 이번 턴 개인 통행료 절반 효과로 처리

# Changelog

## 0.6.2
- 잔꾀 데이터/덱/초기 5장 손패 추가
- F 3배수 보급 추가
- 박수/만신 능력을 짐 카드 기준으로 변경
- 운수의 짐 관련 카드 활성화
- 잔꾀 사용 단계([인물 능력] 이후) 추가

# Changelog

## 0.5.4
- 청약 당첨의 빈 구역 판정을 수정: 구역 전체가 미구매 일반 토지(T2/T3)인 경우에만 후보로 인정
- 악성 토지/특수칸이 섞인 구역을 잘못 빈 구역으로 보는 버그 수정
- 운수 배치 실행 중 `CellKind.MALICIOUS` KeyError 크래시 해결

## 0.5.3
- 운수 타일이 fortune.csv 기반 덱을 공개/해결하도록 연결
- 운수 덱 소진 시 discard 재셔플 처리 추가
- [도착]/[이동]/[효과] 처리 구분 및 운수 유발 이동의 랩 보상 차단 반영
- 즉시 구현 가능한 운수 카드 다수 연결, 잔꾀 의존 카드는 비활성 스텁 유지

## v0.4.0 - 2026-03-24

Current release aligned the simulator with the latest validated rules and added release metadata.

### Added
- Marker-owner card flip flow: when a player acquires the marker, they may flip one character card before the next round's character selection.
- Full logging for `marker_moved`, `marker_flip`, and per-round `active_by_card`.
- Release metadata files: `metadata.py`, `VERSION.txt`, and this changelog.

### Changed
- Character draft choice is randomized in random-character mode.
- Final character selection is randomized in random-character mode.
- Marker flip choice is also randomized in random-character mode, which broadens free-play character coverage to all 16 roles.
- Summary/log outputs now include the simulator version.
- Mark-target selection now only allows players who have not yet taken their turn in the current round.

### Fixed
- Restored seed reproducibility by routing randomized character choices through the engine RNG instead of global `random.choice()`.
- `박수` now calculates income from the target's remaining dice cards.
- `추노꾼` forced movement now preserves `total_steps`, grants no lap credit, and resolves landing effects immediately.
- `자객` now reveals the target immediately and blocks further mark targeting for that round.
- `중매꾼` now stops all follow-up purchase behavior after bankruptcy/game-out.
- `탈출 노비` now receives the 1-step special-tile correction.
- `어사` suppression behavior was reconciled to block only 무뢰-type character skills.

### Validation snapshot
- 1-game and multi-game log validation completed on the random-character branch.
- Broad free-play verification with marker flip randomization confirmed appearance of all 16 characters.

## v0.3.0 - 2026-03-24
- Added marker-driven active character card flip before the next round.
- Added explicit log events for marker movement and active-face changes.

## v0.2.0 - 2026-03-24
- Patched major character-rule inconsistencies for `어사`, `박수`, `추노꾼`, `자객`, `중매꾼`, and `탈출 노비`.
- Added targeted rule-fix tests.

## v0.1.0 - 2026-03-23
- Initial Python simulator baseline with board loop, F/S tiles, dice cards, shards, draft, and turn-order systems.

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.

- v0.7.27: Clarified and tested the swindler rule so tile takeover also transfers the tile's placed victory-point coins; AI now values swindler targets by both monopoly swing and attached coin swing.


## v0.7.29
- Added `debug_cli.py`, a CLI debug runner for human-playable games.
- Supports mixed human/AI play with full hidden-information exposure.
- Prints live event logs and can save full `action_log` JSON for debugging.
## 0.7.41 - 2026-03-25
- Housekeeping pass for cleaner distribution artifacts.
- Normalized packaged source root naming to match current versioning expectations.
- Removed transient caches and stale local run outputs from packaged sources.
- Added `--games` as a CLI alias for `--simulations` in simulation runners.
- Kept runtime behavior, docs integrity, and unit coverage synchronized after cleanup.


## 0.7.41a - 2026-03-25
- Added `CHANGE_WORKFLOW_GUIDE.md`, an internal guide that standardizes how to record intent, scope, files changed, tests, risks, and follow-up work for both small and large changes.
- Updated `MODULE_READ_ORDER.md` so the change workflow guide is read before normal module docs.
- Clarified that rule changes, AI tuning, bug fixes, refactors, and performance work must all leave traceable records in docs and changelog.


## 0.7.44 - External board layout creator
- Added `board_layout_creator.py` to load board layouts from JSON or CSV and convert them into metadata-driven `BoardConfig` instances.
- Added sample `board_layout.json` and `board_layout.csv` files representing the current default 2-3-2 map.
- Added `--board-layout` support to `simulate_with_logs.py` and `run_chunked_batch.py`.
- Added creator tests and doc-integrity tracking for the new loader modules.

## 0.7.48
- moved landing-effect handling for F/S/MALICIOUS/OWN_TILE/UNOWNED landings behind event dispatch boundaries
- added landing effect override tests and kept default behavior via effect_handlers

## 0.7.49
- Finalized remaining high-level event boundaries: `fortune.card.apply`, `fortune.movement.resolve`, and `game.end.evaluate`.
- Added override tests for fortune apply/movement and end evaluation.


## 0.7.50
- Added AI decision hook system and engine-attached AI decision logging.
- Added JSON rule script engine (`rule_script_engine.py`) with default scripts for F landing, cleanup, and end evaluation.
- Added helper-level cleanup/resource trace boundaries and runtime CLI support for `--rule-scripts`.
- Added tests for policy hooks and rule-script overrides.


## 0.7.54
- Added event-bus semantic trace logging into action logs.
- Semantic event names such as `tile.purchase.attempt` and `rent.payment.resolve` are now recorded with summarized context/results when logging is enabled.


## 0.7.55
- Added `METADATA_REGISTRY.md` to document project metadata categories, owners, and update points.
- Added `ACTION_LOG_SCHEMA.md` to formalize raw/semantic/parsed log structure.
- Added `BOARD_LAYOUT_SCHEMA.md` to formalize external board JSON/CSV schema.
- Updated module read order to direct metadata/log/board-schema work through the new registry docs first.
- 0.7.56: retuned control toward mark-profit conversion and token_opt toward token-placement execution.


## 0.7.57
- Updated victory token rules: purchase placement allowed (max 1 on purchased tile).
- Revisit placement remains up to 3 with 3-per-tile cap.
- Takeovers keep placed coins with the tile; monopoly-protected blocks still cannot be taken over.
- Force sale returns placed coins to original owner hand.
- Lap rewards changed to score coins 3 vs shards 3 vs cash 5.

## 0.7.61v3 - 2026-03-29
- live viewer polish: human-play prompt summary, choice preview, mark-state labels, and player panel wording were made more human-readable in Korean.
- live viewer polish: player panels now show hidden trick counts and remaining dice cards more explicitly.

## 0.7.59
- Added external JSON ruleset loading (`ruleset.json`) for injected `GameRules`.
- Added `game_rules_loader.py` and CLI `--ruleset` support in simulation/batch entrypoints.


## 0.7.60
- Rule injection stage 3: economy/resources/dice/special-tile values moved under `GameRules`.
- `ruleset.json` now supports `economy`, `resources`, `dice`, and `special_tiles`.


## 0.7.61v3 - 2026-03-27
- Added an AI audit hotfix for character draft/final selection: `survival_hard_block` now removes blocked growth candidates from the final choice pool when any safe alternative exists.
- Updated README/ai_policy docs to mark `basegame_current_python_code_v7_61_v3_gpt_patch.zip` as the current uploaded baseline and to explain the hard-block semantics explicitly.

- fix: 탐관오리 공납은 대상 조각이 아니라 탐관오리 자신의 조각(//2)을 기준으로 적용하도록 수정했다.
- fix: 어사/탐관오리는 같은 카드이므로 탐관오리 패시브의 불필요한 어사 차단 체크를 제거했다.

- v7.61 v3 GPT winpush2: intended to make GPT recognize Ajeon burst windows on stacked enemy pawns and Gakju lap-engine windows near board end with mobility support.

- Winpush3 intent: after core shard checkpoints, v3_gpt should convert more aggressively into safe growth/coin scoring; favor lap-engine windows for 객주 and allow low-risk T2/T3 buys instead of over-hoarding shards.
