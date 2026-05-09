# simulate_with_logs.py

배치 시뮬레이션 및 JSONL/summary 출력 문서.

## 2026-03-29 AI decision export
- 각 실행은 `games.jsonl`, `errors.jsonl`와 함께 `ai_decisions.jsonl`도 남긴다.
- `ai_decisions.jsonl`에는 AI의 개별 판단 row와 trace payload, run/chunk/game seed 메타데이터가 함께 들어간다.
- 덕분에 전체 `action_log`를 파싱하지 않고도 AI 개선용 후분석을 바로 수행할 수 있다.

## 이번 갱신
- 문서 무결성 요약은 프로세스당 1회만 계산하도록 캐시했다.
- `starting_cash`를 안 바꾸는 기본 실행은 `DEFAULT_CONFIG`를 그대로 재사용해 불필요한 deep copy를 제거했다.
- `run()`은 `emit_summary` 옵션을 지원해 chunk 실행 시 stdout 노이즈를 줄인다.
- `log-level=none`은 summary-only 동작을 유지한다.


Version metadata is sourced from metadata.py, doc integrity is summarized once per process and copied into results, and the CLI accepts both --simulations and --games for the total game count.


## v0.7.44 board layout file input
- Added `--board-layout <path>` CLI option.
- When provided, runtime config loads a JSON/CSV board layout through `board_layout_creator.load_board_config(...)`.
- This allows metadata-driven map swapping without editing `config.py`.


## Board layout loading
`simulate_with_logs.py` supports `--board-layout <json|csv>` and optional `--board-layout-meta <json>` when the tile list comes from CSV and board-level metadata lives in a sidecar JSON file.


## 0.7.50 update
- `simulate_with_logs.py` supports `--rule-scripts` to load alternate JSON rule scripts at runtime.
- Board layout JSON/CSV and rule scripts can now be combined for experiment runs.


## Ruleset override
Use `--ruleset <path>` to load injected `GameRules` from external JSON. This is separate from `--rule-scripts`, which customizes selected event handlers.


### 0.7.61 board/rules separation
`--board-layout` now supports structure-only layouts that rely on `--ruleset`/`ruleset.json` for numeric land values.


## 2026 forensic logging patch
- 게임 결과에 `bankruptcy_events`가 포함된다. 각 이벤트는 `cash_before_death`, `required_cost`, `cash_shortfall`, `cause_hint`, `last_semantic_event`, `is_offturn_death`, `receiver_player_id` 등을 담는다.
- 각 `player_summary` 행에도 `bankruptcy_info`가 들어가서 요약 로그만으로도 해당 플레이어의 파산 원인 힌트를 볼 수 있다.
- 시뮬레이션 로그에는 `run_id`, `root_seed`, `chunk_seed`, `chunk_id`, `chunk_game_id`, `global_game_index`, `game_seed`가 함께 저장된다.
- `run_chunked_batch.py`는 청크 병합 시 `game_id`를 전역 유일값으로 다시 부여하고, 원래 청크 내부 번호는 `chunk_game_id`로 보존한다.


## v7.61 forensic logging patch notes
- Per-game output includes run/chunk/seed metadata for deterministic replay.
- Chunked runs preserve global unique `game_id` and `global_game_index` during merge.


## v7.61 forensic patch notes
- Chunked and single-run outputs preserve replay metadata (`run_id`, seeds, chunk ids, and global indexes).

- Reliability note: running summaries now emit bankruptcy cause/tile-kind aggregates alongside standard end-reason statistics for easier forensic comparison across runs.

## 2026-05-09 contract sync
Simulation result dictionaries include `weather_history`, AI decision rows, and bankruptcy forensic fields used by downstream stability gates. Keep summary tests synchronized with result fields.
