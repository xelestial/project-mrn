# test_draft_three_players.py

## 역할
3인 생존 시 특수 드래프트 규칙을 검증한다.

## 설계 의도
- 4인 규칙이 3인 상황에 잘못 그대로 적용되는 회귀를 막는다.
- 제외 카드 1장, 보조 4장, 역순 선택, 생존자만 최종 인물 선택이라는 특수 규칙을 고정한다.

- 수정 규칙: 대응 소스 수정 시 이 문서도 함께 갱신한다.
Bootstrap note: tests pin the engine directory on import so runtime modules resolve consistently.
