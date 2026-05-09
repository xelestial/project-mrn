# compare_policies.py

## 역할
주 정책(`random`, `heuristic_v1`, 이후 v2 계열)을 같은 seed 세트로 비교해 delta 리포트를 만든다.

## 설계 의도
- "더 좋아졌다"를 감으로 말하지 않고, 평균 턴/F/파산률/우승자 전략 평균 차이로 정량 검증한다.

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.

## 2026-05-09 contract sync
- Policy comparison remains an engine-only benchmark surface. When decision keys or reward-rule parameters change, compare runs must use the same manifest-visible ruleset values as the server/front adapters.
