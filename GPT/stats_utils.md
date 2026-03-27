# stats_utils.py

## 역할
상세 로그/요약에서 공통 통계를 계산하는 유틸리티를 모아둔 모듈이다.

## 설계 의도
- 우승자 평균, 비우승자 평균, 전략 통계, 랩 선택 비율, 잔꾀 사용 수 같은 리포트 계산을 한곳에 모은다.
- 새 통계를 추가할 때는 이 파일과 비교 스크립트 둘 다 같이 갱신해야 한다.
- 현재는 1등/2등 평균 점수 외에 1등/2등 평균 랩 수, 평균 랩 보상 횟수, 전체 지목 성공률도 계산한다.

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.

- Reliability note: `compute_basic_stats_from_games` now prefers `character_choice_counts` for pick-frequency stats, falls back to stable last-selected character fields for seat-level summaries, and records missing/null-field reliability counters.
