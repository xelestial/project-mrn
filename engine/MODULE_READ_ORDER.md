# MODULE_READ_ORDER.md

## 우선 읽기 규칙
## 최우선 공통 문서
- 작업을 시작하기 전에 `CHANGE_WORKFLOW_GUIDE.md`를 먼저 읽는다.
- 메타데이터/로그/외부 보드 스펙을 건드릴 때는 `METADATA_REGISTRY.md`, `ACTION_LOG_SCHEMA.md`, `BOARD_LAYOUT_SCHEMA.md`를 먼저 확인한다.
- 이후 이 문서의 `*.md -> *.py` 순서를 따른다.

이 프로젝트를 다시 읽을 때는 **항상 대응하는 `.md` 문서를 먼저 읽고**, 그 다음 소스 파일을 열어야 한다.
예: `engine.md -> engine.py`, `ai_policy.md -> ai_policy.py`

## 이유
- 규칙 의도와 현재 엔진 동작은 비슷하지만 항상 같지는 않다.
- 최근 수정 포인트, 회귀 위험, 실험용 정책 의도는 코드보다 문서에 먼저 정리한다.
- 따라서 문서를 먼저 읽으면 규칙/정책/실험 의도를 더 빠르게 복구할 수 있다.

## 무결성 규칙
- 소스(`.py`)를 수정하면 대응하는 문서(`.md`)도 함께 수정해야 한다.
- 무결성 검사는 `doc_integrity.py`, `print_settings.py`, `test_config_settings.py`, `test_doc_integrity.py`에서 수행한다.
- 기준은 **문서 수정 시각이 소스 수정 시각보다 같거나 더 최신**이어야 한다.

## 문서 대상
- `ai_policy.md` -> `ai_policy.py`
- `analyze_strategy_logs.md` -> `analyze_strategy_logs.py`
- `board_layout_creator.md` -> `board_layout_creator.py`
- `characters.md` -> `characters.py`
- `compare_lap_policies.md` -> `compare_lap_policies.py`
- `compare_mixed_lap_policies.md` -> `compare_mixed_lap_policies.py`
- `compare_policies.md` -> `compare_policies.py`
- `config.md` -> `config.py`
- `engine.md` -> `engine.py`
- `fortune_cards.md` -> `fortune_cards.py`
- `main.md` -> `main.py`
- `metadata.md` -> `metadata.py`
- `print_settings.md` -> `print_settings.py`
- `simulate_with_logs.md` -> `simulate_with_logs.py`
- `state.md` -> `state.py`
- `stats_utils.md` -> `stats_utils.py`
- `test_board_layout_creator.md` -> `test_board_layout_creator.py`
- `test_config_settings.md` -> `test_config_settings.py`
- `test_draft_three_players.md` -> `test_draft_three_players.py`
- `test_rule_fixes.md` -> `test_rule_fixes.py`
- `trick_cards.md` -> `trick_cards.py`

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.

- `weather_cards.md` -> `weather_cards.py`

- For board shape/rule changes, read `board_layout_creator.md` before `config.py`.

- event_system.md -> event_system.py
- effect_handlers.md -> effect_handlers.py


### Added in 0.7.50
Read `rule_script_engine.md` and `policy_hooks.md` after `event_system.md` when working on runtime behavior.

- Read `game_rules.md` before changing token/lap/takeover/end-condition logic.
- Read `test_rules_injection.md` when modifying injected rule behavior.

- If the task changes rulesets, read `game_rules.md` and `game_rules_loader.md` before editing config/runtime entrypoints.

- survival_common.py / survival_common.md: 공용 생존 규칙과 액션 생존 가드 임계값을 정의한다.
