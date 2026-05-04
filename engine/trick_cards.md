# trick_cards.py

## 0.7.62 note
Trick-card runtime helpers continue to support burden-aware evaluation used by control-profile cleanup and mark-pressure scoring.

잔꾀 카드 CSV 로드/덱 생성 문서.

## 이번 갱신
- CSV 경로 해석을 공통화했다.
- 정의 로드와 덱 빌드를 캐시해서 반복 시뮬레이션 시 디스크 I/O를 줄인다.
- 반환값은 여전히 fresh list다.
