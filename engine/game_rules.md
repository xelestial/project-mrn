# game_rules.py

룰 주입 1단계 모듈.

## 목적

엔진/핸들러/AI가 전역 상수나 개별 config 필드만 직접 참조하지 않고, `GameRules` 집합을 통해 토큰/랩 보상/인수/강제 매각/종료 조건을 주입받게 한다.

## 구성

- `TokenRules`
  - 토큰 시작 개수, 랩 보상 토큰 수, 구매 시 배치 가능 여부, 타일 최대치
- `LapRewardRules`
  - 현금/토큰/조각 랩 보상 수치
- `TakeoverRules`
  - 독점 상태 인수 차단 여부, 토큰 동반 이전 여부
- `ForceSaleRules`
  - 강제 매각 환불/토큰 복귀/재구매 차단 여부
- `EndConditionRules`
  - F 종료값, 독점 종료, 타일 종료, 생존자 종료
- `GameRules`
  - 위 룰 객체를 묶고, 기존 config mirror 필드와 상호 동기화

## 현재 적용 범위

- `state.py`: 시작 손 토큰
- `engine.py`: 토큰 배치, 인수, 강제 매각, 종료 판정
- `effect_handlers.py`: 랩 보상, 구매 시 첫 배치
- `ai_policy.py`: 토큰 최대치/종료 타일 수 참조

## 의도

향후 `WeatherRules`, `MovementRules`, `FortuneRules` 등으로 확장해, 실험용 룰셋을 엔진과 AI에 같은 방식으로 주입한다.


## Config mirror sync
`GameRules` synchronizes explicit injected rules back into `config.coins/shards/end/board` mirror fields so rule consumers can read consistent mirror values.


## 0.7.60 note
`GameRules` now also carries `economy`, `resources`, `dice`, and `special_tiles` sections so modules can consume injected rule values instead of reading config mirror fields directly.


### 0.7.61 economy profiles
`EconomyRules` now resolves tile purchase/rent through `land_profiles` when a tile is defined structurally with an `economy_profile` key.
