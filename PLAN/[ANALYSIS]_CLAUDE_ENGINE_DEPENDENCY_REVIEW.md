# [ANALYSIS] Engine Dependency Review

Status: `ANALYSIS`
Role: `engine 및 게임 구조의 의존성 현황 검토 — 개선 필요 여부 판단`
Date: 2026-03-28
Author: Claude Sonnet 4.6

## 검토 범위

AI 전략 판단 코드(ai_policy, policy/*)를 제외한 엔진 포함 게임 구조 전체.

- `engine.py`
- `config.py`
- `state.py`
- `characters.py`
- `fortune_cards.py`, `trick_cards.py`, `weather_cards.py`
- `effect_handlers.py`
- `rule_script_engine.py`
- `event_system.py`
- `simulate_with_logs.py`
- `board_layout_creator.py`, `game_rules_loader.py`
- `doc_integrity.py`, `metadata.py`, `stats_utils.py`

## 의존성 현황

순환 의존성 없음 (clean acyclic graph).

허브 모듈 (참조 횟수):
- `config` — 6곳에서 import
- `characters` — 4곳
- `weather_cards` — 4곳
- `state` — 3곳

engine.py가 11개 로컬 모듈을 직접 import하는 중심 오케스트레이터 구조.

## 문제로 보이지만 실제로는 아닌 것들

### 1. engine.py 크기와 import 수

11개 import 중 대부분이 `fortune_cards`, `trick_cards`, `weather_cards`, `characters`, `config`, `state` 같은 안정된 leaf 모듈이다. 이들은 서로 의존하지 않고 거의 변경되지 않는다.

엔진을 더 잘게 분리하면 오케스트레이터 계층만 늘어날 뿐이다. 현재 pain point가 없으므로 건드릴 이유가 없다.

### 2. config.py 초기화 시 파일 I/O

`GameConfig.__post_init__()`이 `load_ruleset()`을 호출하고, `DEFAULT_CONFIG`가 모듈 import 시 생성된다. 이론적으로 side effect가 있다.

그러나 `simulate_with_logs._runtime_config()`와 `battle.py`에서 이미 경로 오버라이드 패턴이 존재한다. 현재 코드 흐름에서 문제가 된 적 없음.

### 3. engine 내부 mutable state

`_action_log`, `_strategy_stats` 등 인스턴스 변수들이 게임 진행 중 변경된다. 게임 인스턴스 하나당 하나의 engine 인스턴스를 생성하는 현재 패턴에서는 문제없다. 병렬 실행이 필요한 시점이 오면 그때 다루면 된다.

### 4. 하드코딩 파일 경로

`fortune.csv`, `trick.csv`, `weather.csv` 등이 default 값으로 박혀 있다. 이미 인자로 오버라이드 가능하므로 실제 문제가 된 적 없음.

## 합리적인 이유가 있는 한 가지

### BasePolicy Protocol 부재

현재 engine.py는 policy 인터페이스를 `hasattr()` 체크로 확인한다.

```python
# engine.py 현재 패턴
if hasattr(self.policy, "set_rng"):
    self.policy.set_rng(rng)
if hasattr(self.policy, "register_policy_hook"):
    self.policy.register_policy_hook(...)
```

이것이 시각화 작업에서 직접 문제가 된다:

- `SHARED_VISUAL_RUNTIME_CONTRACT`가 `HumanDecisionAdapter`와 `AIDecisionAdapter`를 명시했다
- 이 어댑터들이 engine이 호출하는 `choose_*` 메서드 전체를 구현해야 한다
- 공식 Protocol 없이는 어댑터 구현자가 engine 소스를 일일이 뒤져서 필요한 메서드를 파악해야 한다
- GPT와 Claude가 각자 어댑터를 구현할 때 누락 메서드가 발생할 가능성이 있다

**제안:**

```python
# CLAUDE/base_policy.py (신규)
from typing import Protocol, runtime_checkable

@runtime_checkable
class BasePolicy(Protocol):
    def choose_movement(self, state, player) -> ...: ...
    def choose_draft_card(self, state, player, offered_cards) -> ...: ...
    def choose_final_character(self, state, player, card_choices) -> ...: ...
    def choose_lap_reward(self, state, player) -> ...: ...
    def choose_trick_to_use(self, state, player, hand) -> ...: ...
    def choose_hidden_trick_card(self, state, player, hand) -> ...: ...
    def choose_mark_target(self, state, player, actor_name) -> ...: ...
    def choose_coin_placement_tile(self, state, player) -> ...: ...
    def choose_geo_bonus(self, state, player, char) -> ...: ...
    def choose_doctrine_relief_target(self, state, player, candidates) -> ...: ...
    def choose_purchase_tile(self, state, player, pos, cell, cost, *, source) -> ...: ...
    def choose_specific_trick_reward(self, state, player, choices) -> ...: ...
    def choose_burden_exchange_on_supply(self, state, player, card) -> ...: ...
    def choose_active_flip_card(self, state, player, flippable_cards) -> ...: ...
```

**engine.py는 수정하지 않는다.** Protocol은 강제 상속이 아니라 계약 명세 문서로서 역할을 한다. `isinstance(policy, BasePolicy)` 검사를 원할 때만 사용한다.

**적용 시기:** 시각화 Phase 1-S 진입 전 또는 `HumanDecisionAdapter` 구현 시작 직전.

**작업량:** `base_policy.py` 파일 하나 추가. engine.py 무수정.

## 결론

| 항목 | 조치 | 이유 |
|---|---|---|
| engine.py 분리 | 불필요 | pain point 없음, 리스크만 있음 |
| config 초기화 | 불필요 | override 패턴 이미 존재 |
| engine 내부 state | 불필요 | 현재 사용 패턴에서 문제 없음 |
| 하드코딩 경로 | 불필요 | 이미 오버라이드 가능 |
| BasePolicy Protocol | **선택적 추가** | 시각화 어댑터 구현의 계약 명세 역할 |

현재 엔진 구조는 현재 요구사항에 적합하다. 대규모 리팩터링 없이 시각화 Phase 1-S로 진입 가능하다.
