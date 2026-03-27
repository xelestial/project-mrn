# analyze_strategy_logs.py

## 역할
`games.jsonl` 상세 로그를 읽어 `stats_utils.compute_basic_stats_from_games()`로 기본 통계를 산출한다.

## 설계 의도
- 배치 시뮬레이션 후 빠르게 통계만 재계산하고 싶을 때 사용하는 오프라인 분석 도구다.
- 엔진을 다시 돌리지 않고도 우승자/비우승자 평균 전략치를 재구성할 수 있도록 한다.

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.
