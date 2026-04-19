# test_config_settings.py

설정/메타데이터/요약 관련 회귀 테스트 문서.

## 이번 갱신
- 기본 보드 검증은 더 이상 특정 절대 좌표를 가정하지 않는다.
- 한 변의 토지 비용/통행료는 메타데이터에서 동적으로 찾은 side land positions로 확인한다.
- tile metadata(`purchase_cost`, `rent_cost`, `zone_color`)도 기본 설정 테스트에 포함한다.


## v0.7.44 note
- Config tests still verify default values, but board-shape-specific validation should prefer metadata-driven lookup and the dedicated creator tests.

- v0.7.56: added tests for control mark-profit preference and token-opt placement execution behaviour.

- 0.7.56: added profile-intent regression tests for control mark-profit and token_opt placement execution.


## 0.7.57
Default config assertions now cover lap reward values 5/3/3 and purchase-time token placement enablement.

- Added summary reliability coverage for missing final characters, null numeric fields, and character-choice-count based aggregation.
Bootstrap note: tests pin their own package directory on import so GPT and CLAUDE suites can run together without cross-package module reuse.
