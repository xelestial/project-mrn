# test_rules_injection.py

`GameRules` 주입 구조의 회귀 테스트.

## 검증 항목

- 커스텀 랩 보상 수치가 엔진에 반영되는지
- 커스텀 종료 조건이 엔진에 반영되는지
- 강제 매각 룰을 껐을 때 환불/토큰 복귀/재구매 차단이 바뀌는지
- 독점 인수 차단을 껐을 때 실제 인수가 가능한지
- `GameRules` 값이 `config.coins/shards/end/...` mirror 필드와 동기화되는지


## Coverage note
The test suite checks both explicit injection behavior and config mirror field synchronization.


## 0.7.60 note
Coverage now includes stage 3 sync checks for economy/resources/dice/special-tile rule injection.
Bootstrap note: tests pin the engine directory on import so runtime modules resolve consistently.

- 2026-04-15 sync: custom lap reward injection coverage now pins `points_budget` and `coins_point_cost` alongside reward amount so the injected four-coin payout remains legal under the stage-3 budget rules.
